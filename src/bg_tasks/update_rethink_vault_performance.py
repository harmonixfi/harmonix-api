import logging
import uuid
from datetime import datetime, timedelta, timezone

import click
import numpy as np
import pandas as pd
import pendulum
from sqlalchemy import func
from sqlmodel import Session, not_, select
from web3.contract import Contract

from bg_tasks.utils import get_before_price_per_shares
from core.config import settings
from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models import Vault
from models.pps_history import PricePerShareHistory
from models.user_portfolio import UserPortfolio
from models.vault_performance import VaultPerformance
from models.vaults import NetworkChain, VaultCategory
from schemas.fee_info import FeeInfo
from utils.web3_utils import get_current_pps, get_vault_contract, get_current_tvl

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("update_rethink_vault_performance")

session = Session(engine)

def get_fee_info():
    fee_structure = [0, 0, 10, 1]
    fee_info = FeeInfo(
        deposit_fee=fee_structure[0],
        exit_fee=fee_structure[1],
        performance_fee=fee_structure[2],
        management_fee=fee_structure[3],
    )
    return fee_info.model_dump_json()

def calculate_roi(after: float, before: float, days: int) -> float:
    tvl_delta = (after - before) / (before or 1)
    annualized_roi = (1 + tvl_delta) ** (365.2425 / days) - 1
    return annualized_roi

def get_historical_tvl(vault_id: uuid.UUID, days_ago: int) -> float:
    target_date = pendulum.now(tz=pendulum.UTC) - timedelta(days=days_ago)
    
    # Get the VaultPerformance record closest to but before the target date
    historical_performance = session.exec(
        select(VaultPerformance)
        .where(VaultPerformance.vault_id == vault_id)
        .where(VaultPerformance.datetime <= target_date)
        .order_by(VaultPerformance.datetime.desc())
        .limit(1)
    ).first()

    return historical_performance.total_locked_value if historical_performance else None


def update_price_per_share(vault_id: uuid.UUID, current_price_per_share: float):
    # update today to hour with minute = 0 and second = 0
    today = pendulum.now(tz=pendulum.UTC).replace(minute=0, second=0, microsecond=0)

    # Check if a PricePerShareHistory record for today already exists
    existing_pps = session.exec(
        select(PricePerShareHistory).where(
            PricePerShareHistory.vault_id == vault_id,
            PricePerShareHistory.datetime == today,
        )
    ).first()

    if existing_pps:
        # If a record for today already exists, update the price per share
        existing_pps.price_per_share = current_price_per_share
    else:
        # If no record for today exists, create a new one
        new_pps = PricePerShareHistory(
            datetime=today, price_per_share=current_price_per_share, vault_id=vault_id
        )
        session.add(new_pps)

    session.commit()


def calculate_tvl_statistics(vault_id: uuid.UUID):
    # Get historical TVL data
    performances = session.exec(
        select(VaultPerformance)
        .where(VaultPerformance.vault_id == vault_id)
        .order_by(VaultPerformance.datetime.asc())
    ).all()

    if not performances:
        return 0, 0, 0, 0

    # Create DataFrame with TVL data
    df = pd.DataFrame([
        {"datetime": p.datetime, "tvl": p.total_locked_value}
        for p in performances
    ])
    df.set_index("datetime", inplace=True)
    df.sort_index(inplace=True)
    
    # Calculate percentage changes
    df["pct_change"] = df["tvl"].pct_change()
    
    all_time_high_tvl = None
    
    # Calculate risk metrics
    returns = df["pct_change"].dropna().values
    
    # Calculate Sortino ratio
    risk_free_rate = 0
    excess_returns = returns - risk_free_rate
    downside_returns = np.where(returns < risk_free_rate, returns - risk_free_rate, 0)
    downside = np.sqrt(np.mean(np.square(downside_returns)))
    sortino = np.mean(excess_returns) / downside if downside != 0 else 0
    
    # Calculate risk factor (standard deviation of negative returns)
    negative_returns = returns[returns < 0]
    risk_factor = np.std(negative_returns) if len(negative_returns) > 0 else 0

    return all_time_high_tvl, sortino, downside, risk_factor

def calculate_performance(vault: Vault, vault_contract: Contract):
    current_price_per_share = get_current_pps(vault_contract, decimals=1e18)
    current_tvl = get_current_tvl(vault_contract, decimals=1e18)
    fee_info = get_fee_info()

    # Calculate Monthly APY
    month_ago_price_per_share = get_before_price_per_shares(session, vault.id, days=30)
    month_ago_datetime = pendulum.instance(month_ago_price_per_share.datetime).in_tz(
        pendulum.UTC
    )

    time_diff = pendulum.now(tz=pendulum.UTC) - month_ago_datetime
    days = min((time_diff).days, 30) if time_diff.days > 0 else time_diff.hours / 24
    monthly_apy = calculate_roi(current_price_per_share, month_ago_price_per_share.price_per_share, days=days)
    monthly_apy *= 100

    week_ago_price_per_share = get_before_price_per_shares(session, vault.id, days=7)
    week_ago_datetime = pendulum.instance(week_ago_price_per_share.datetime).in_tz(
        pendulum.UTC
    )
    time_diff = pendulum.now(tz=pendulum.UTC) - week_ago_datetime
    days = min(time_diff.days, 7) if time_diff.days > 0 else time_diff.hours / 24
    weekly_apy = calculate_roi(
        current_price_per_share, week_ago_price_per_share.price_per_share, days=days
    )
    weekly_apy *= 100

    # Calculate YTD APY
    start_of_year = pendulum.now(tz=pendulum.UTC).start_of('year')
    ytd_tvl = get_historical_tvl(vault.id, days_ago=(pendulum.now(tz=pendulum.UTC) - start_of_year).days)
    if ytd_tvl:
        apy_ytd = calculate_roi(
            current_tvl,
            ytd_tvl,
            days=(pendulum.now(tz=pendulum.UTC) - start_of_year).days,
        ) * 100
    else:
        apy_ytd = 0

    # Calculate risk statistics using TVL
    all_time_high_tvl, sortino, downside, risk_factor = calculate_tvl_statistics(vault.id)

    update_price_per_share(vault.id, current_price_per_share)

    # Count unique depositors
    count = session.scalar(
        select(func.count())
        .select_from(UserPortfolio)
        .where(UserPortfolio.vault_id == vault.id)
    )

    # Create performance record
    return VaultPerformance(
        datetime=datetime.now(timezone.utc),
        total_locked_value=current_tvl,
        apy_1m=monthly_apy,
        apy_1w=weekly_apy,
        apy_ytd=apy_ytd,
        vault_id=vault.id,
        risk_factor=risk_factor,
        all_time_high_tvl=all_time_high_tvl,
        sortino_ratio=sortino,
        downside_risk=downside,
        unique_depositors=count,
        fee_structure=fee_info,
        benchmark=0,
        pct_benchmark=0
    )

@click.command()
@click.option("--chain", default="arbitrum_one", help="Blockchain network to use")
def main(chain: str):
    try:
        setup_logging_to_console()
        setup_logging_to_file(f"update_rethink_vault_performance_{chain}", logger=logger)
        
        network_chain = NetworkChain[chain.lower()]
        
        # Get active Rethink vaults
        vaults = session.exec(
            select(Vault)
            .where(Vault.category == VaultCategory.real_yield_v2)
            .where(Vault.is_active == True)
            .where(Vault.network_chain == network_chain)
        ).all()

        for vault in vaults:
            logger.info("Updating performance for %s...", vault.name)
            vault_contract, _ = get_vault_contract(vault, abi_name="rethink_yield_v2")

            new_performance_rec = calculate_performance(vault, vault_contract)
            session.add(new_performance_rec)

            # Update vault metrics
            vault.ytd_apy = new_performance_rec.apy_ytd
            vault.monthly_apy = new_performance_rec.apy_1m
            vault.weekly_apy = new_performance_rec.apy_1w
            vault.tvl = new_performance_rec.total_locked_value

            logger.info(
                "Vault %s: tvl = %s, monthly_apy = %s",
                vault.name,
                vault.tvl,
                vault.monthly_apy,
            )
            session.commit()

    except Exception as e:
        logger.error(
            "An error occurred while updating Rethink vault performance: %s",
            e,
            exc_info=True,
        )
        raise e

if __name__ == "__main__":
    main()