import logging
import uuid
from datetime import datetime, timedelta, timezone

import click
import pandas as pd
import pendulum
import seqlog
from sqlalchemy import func
from sqlmodel import Session, not_, or_, select
from web3 import Web3
from web3.contract import Contract

from bg_tasks.update_delta_neutral_vault_performance_daily import calculate_reward_apy
from bg_tasks.utils import (
    calculate_pps_statistics,
    calculate_roi,
    get_before_price_per_shares,
)
from core import constants
from core.abi_reader import read_abi
from core.config import settings
from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models import Vault
from models.apy_component import APYComponent
from models.point_distribution_history import PointDistributionHistory
from models.pps_history import PricePerShareHistory
from models.user_portfolio import UserPortfolio
from models.vault_apy_breakdown import VaultAPYBreakdown
from models.vault_performance import VaultPerformance
from models.vaults import NetworkChain
from schemas.fee_info import FeeInfo
from schemas.vault_state import VaultState, VaultStatePendle
from services import pendle_service
from services.hyperliquid_service import (
    get_avg_8h_funding_rate,
)
from services.market_data import get_price
from utils.vault_utils import calculate_projected_apy
from utils.web3_utils import get_vault_contract, get_current_pps, get_current_tvl

# # Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("update_pendle_hedging_vault_performance_daily")

session = Session(engine)
token_abi = read_abi("ERC20")


def get_price_per_share_history(vault_id: uuid.UUID) -> pd.DataFrame:
    pps_history = session.exec(
        select(PricePerShareHistory)
        .where(PricePerShareHistory.vault_id == vault_id)
        .order_by(PricePerShareHistory.datetime.asc())
    ).all()

    # Convert the list of PricePerShareHistory objects to a DataFrame
    pps_history_df = pd.DataFrame([vars(pps) for pps in pps_history])

    return pps_history_df[["datetime", "price_per_share", "vault_id"]]


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


def get_fee_info():
    fee_structure = [0, 0, 10, 1]
    fee_info = FeeInfo(
        deposit_fee=fee_structure[0],
        exit_fee=fee_structure[1],
        performance_fee=fee_structure[2],
        management_fee=fee_structure[3],
    )
    json_fee_info = fee_info.model_dump_json()
    return json_fee_info


def get_vault_state(vault_contract: Contract, owner_address: str):
    state = vault_contract.functions.getVaultState().call(
        {"from": Web3.to_checksum_address(owner_address)}
    )
    vault_state = VaultStatePendle(
        old_pt_token_address=state[0],
        pps=state[1] / 1e6,
        pt_withdraw_pool_amount=state[2] / 1e18,
        sc_withdraw_pool_amount=state[3] / 1e6,
        total_pt_amount=state[4] / 1e18,
        total_shares=state[5] / 1e6,
        total_fee_pool_amount=state[6] / 1e6,
        last_update_management_fee_date=state[7],
    )
    return vault_state


def get_next_friday():
    today = pendulum.now(tz=pendulum.UTC)
    next_friday = today.next(pendulum.FRIDAY)
    next_friday = next_friday.replace(hour=8, minute=0, second=0, microsecond=0)
    return next_friday


def get_next_day():
    today = pendulum.now(tz=pendulum.UTC).today()
    next_day = today.add(days=1)
    next_day = next_day.replace(hour=8, minute=0, second=0, microsecond=0)
    return next_day


def calculate_apy_ytd(vault_id, current_price_per_share):
    now = pendulum.now(tz=pendulum.UTC)
    vault = session.exec(select(Vault).where(Vault.id == vault_id)).first()

    # Get the start of the year or the first logged price per share
    start_of_year = pendulum.datetime(now.year, 1, 1, tz="UTC")
    price_per_share_start = session.exec(
        select(PricePerShareHistory)
        .where(
            PricePerShareHistory.vault_id == vault.id
            and PricePerShareHistory.datetime >= start_of_year
        )
        .order_by(PricePerShareHistory.datetime.asc())
    ).first()

    prev_pps = price_per_share_start.price_per_share if price_per_share_start else 1

    # Calculate the APY
    apy_ytd = calculate_roi(
        current_price_per_share,
        prev_pps,
        days=(now - start_of_year).days,
    )

    return apy_ytd


def get_earned_hl_point(vault: Vault):
    # Get the latest point distribution for Hyperliquid
    point_dist = session.exec(
        select(PointDistributionHistory)
        .where(PointDistributionHistory.vault_id == vault.id)
        .where(PointDistributionHistory.partner_name == constants.HYPERLIQUID)
        .order_by(PointDistributionHistory.created_at.desc())
    ).first()
    if not point_dist:
        return 0

    return point_dist.point


# Step 4: Calculate Performance Metrics
def calculate_performance(
    vault: Vault,
    vault_contract: Contract,
    owner_address: str,
    update_freq: str = "daily",
):
    current_price = get_price("ETHUSDT")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    current_price_per_share = get_current_pps(vault_contract)
    total_balance = get_current_tvl(vault_contract)
    fee_info = get_fee_info()
    vault_state = get_vault_state(vault_contract, owner_address=owner_address)

    weekly_reward_apy = 0
    monthly_reward_apy = 0
    apy_reward_15day = 0
    apy_reward_45day = 0
    if vault.slug == constants.PENDLE_RSETH_26JUN25_SLUG:
        weekly_reward_apy, monthly_reward_apy, apy_reward_15day, apy_reward_45day = (
            calculate_reward_apy(vault.id, total_balance)
        )
        logger.info(
            "Reward APY calculated - Weekly: %.2f%%, Monthly: %.2f%%",
            weekly_reward_apy,
            monthly_reward_apy,
        )

    # Calculate Monthly APY
    month_ago_price_per_share = get_before_price_per_shares(session, vault.id, days=30)
    month_ago_datetime = pendulum.instance(month_ago_price_per_share.datetime).in_tz(
        pendulum.UTC
    )

    time_diff = pendulum.now(tz=pendulum.UTC) - month_ago_datetime
    days = min((time_diff).days, 30) if time_diff.days > 0 else time_diff.hours / 24
    monthly_apy = calculate_roi(
        current_price_per_share, month_ago_price_per_share.price_per_share, days=days
    )

    pendle_data = pendle_service.get_market(
        constants.CHAIN_IDS["CHAIN_ARBITRUM"], vault.pt_address
    )
    if pendle_data:
        pendle_market_data = pendle_data[0]
    if pendle_market_data:
        monthly_apy += pendle_market_data.implied_apy / 2

    week_ago_price_per_share = get_before_price_per_shares(session, vault.id, days=7)
    week_ago_datetime = pendulum.instance(week_ago_price_per_share.datetime).in_tz(
        pendulum.UTC
    )
    time_diff = pendulum.now(tz=pendulum.UTC) - week_ago_datetime
    days = min(time_diff.days, 7) if time_diff.days > 0 else time_diff.hours / 24
    weekly_apy = calculate_roi(
        current_price_per_share, week_ago_price_per_share.price_per_share, days=days
    )

    apy_ytd = calculate_apy_ytd(vault.id, current_price_per_share)

    # apy 15days
    price_per_share_15_days_ago = get_before_price_per_shares(
        session, vault.id, days=15
    )
    datetime_15_days_ago = pendulum.instance(
        price_per_share_15_days_ago.datetime
    ).in_tz(pendulum.UTC)
    time_diff = pendulum.now(tz=pendulum.UTC) - datetime_15_days_ago
    days_15 = min(time_diff.days, 15) if time_diff.days > 0 else time_diff.hours / 24
    apy_15d = calculate_roi(
        current_price_per_share,
        price_per_share_15_days_ago.price_per_share,
        days=days_15,
    )

    # apy 45days
    price_per_share_45_days_ago = get_before_price_per_shares(
        session, vault.id, days=45
    )
    datetime_45_days_ago = pendulum.instance(
        price_per_share_45_days_ago.datetime
    ).in_tz(pendulum.UTC)
    time_diff = pendulum.now(tz=pendulum.UTC) - datetime_45_days_ago
    days_45 = min(time_diff.days, 45) if time_diff.days > 0 else time_diff.hours / 24
    apy_45d = calculate_roi(
        current_price_per_share,
        price_per_share_45_days_ago.price_per_share,
        days=days_45,
    )

    performance_history = session.exec(
        select(VaultPerformance).order_by(VaultPerformance.datetime.asc()).limit(1)
    ).first()

    benchmark = current_price
    benchmark_percentage = ((benchmark / performance_history.benchmark) - 1) * 100
    # Add reward APY to base APY
    apy_1m = monthly_apy * 100 + monthly_reward_apy
    apy_1w = weekly_apy * 100 + weekly_reward_apy
    apy_15d = apy_15d * 100 + apy_reward_15day
    apy_45d = apy_45d * 100 + apy_reward_45day
    apy_ytd = apy_ytd * 100

    all_time_high_per_share, sortino, downside, risk_factor = calculate_pps_statistics(
        session, vault.id
    )

    # count all portfolio of vault
    statement = (
        select(func.count())
        .select_from(UserPortfolio)
        .where(UserPortfolio.vault_id == vault.id)
    )
    count = session.scalar(statement)

    # Create a new VaultPerformance object
    performance = VaultPerformance(
        datetime=datetime.now(timezone.utc),
        total_locked_value=total_balance,
        benchmark=benchmark,
        pct_benchmark=benchmark_percentage,
        apy_1m=apy_1m,
        base_monthly_apy=monthly_apy * 100,
        reward_monthly_apy=monthly_reward_apy,
        apy_1w=apy_1w,
        base_weekly_apy=weekly_apy * 100,
        reward_weekly_apy=weekly_reward_apy,
        apy_ytd=apy_ytd,
        vault_id=vault.id,
        risk_factor=risk_factor,
        all_time_high_per_share=all_time_high_per_share,
        total_shares=vault_state.total_shares,
        sortino_ratio=sortino,
        downside_risk=downside,
        unique_depositors=count,
        earned_fee=vault_state.total_fee_pool_amount,
        fee_structure=fee_info,
        apy_15d=apy_15d,
        apy_45d=apy_45d,
    )

    update_price_per_share(vault.id, current_price_per_share)

    return performance


# Main Execution
@click.command()
@click.option("--chain", default="arbitrum_one", help="Blockchain network to use")
def main(chain: str):
    try:
        setup_logging_to_console()
        setup_logging_to_file(
            f"update_pendle_hedging_vault_performance_daily_{chain}", logger=logger
        )
        # Parse chain to NetworkChain enum
        network_chain = NetworkChain[chain.lower()]
        vaults = session.exec(
            select(Vault)
            .where(Vault.strategy_name == constants.PENDLE_HEDGING_STRATEGY)
            .where(Vault.is_active == True)
            .where(Vault.network_chain == network_chain)
            .where(not_(Vault.tags.contains("ended")))
        ).all()

        for vault in vaults:
            logger.info("Updating performance for %s...", vault.name)
            vault_contract, _ = get_vault_contract(vault, "pendlehedging")

            new_performance_rec = calculate_performance(
                vault,
                vault_contract,
                vault.owner_wallet_address,
                update_freq=(
                    "daily"
                    if network_chain in {NetworkChain.arbitrum_one, NetworkChain.base}
                    else "weekly"
                ),
            )
            # Add the new performance record to the session and commit
            session.add(new_performance_rec)

            # Update the vault with the new information
            vault.ytd_apy = new_performance_rec.apy_ytd
            vault.monthly_apy = new_performance_rec.apy_1m
            vault.weekly_apy = new_performance_rec.apy_1w
            vault.tvl = new_performance_rec.total_locked_value
            vault.next_close_round_date = None
            logger.info(
                "Vault %s: tvl = %s, apy %s", vault.name, vault.tvl, vault.monthly_apy
            )

            session.commit()
    except Exception as e:
        logger.error(
            "An error occurred while updating delta neutral performance: %s",
            e,
            exc_info=True,
        )
        raise e


if __name__ == "__main__":
    main()
