import logging
import uuid
from datetime import datetime, timezone

import pandas as pd
import numpy as np
import pendulum
from sqlalchemy import func
from sqlmodel import Session, select
from web3.contract import Contract

from bg_tasks.utils import sortino_ratio, downside_risk, calculate_risk_factor
from core import constants
from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models import Vault
from models.pps_history import PricePerShareHistory
from models.user_portfolio import UserPortfolio
from models.vault_performance import VaultPerformance
from models.vaults import NetworkChain
from schemas.fee_info import FeeInfo
from services.market_data import get_price
from utils.web3_utils import get_vault_contract, get_current_pps, get_current_tvl
from services import solv_service

# # Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("update_delta_neutral_vault_performance_daily")


session = Session(engine)


def get_fee_info():
    fee_structure = [0, 0, 0, 1]
    fee_info = FeeInfo(
        deposit_fee=fee_structure[0],
        exit_fee=fee_structure[1],
        performance_fee=fee_structure[2],
        management_fee=fee_structure[3],
    )
    json_fee_info = fee_info.model_dump_json()
    return json_fee_info


def calculate_pps_statistics_from_solv(df: pd.DataFrame):
    df.set_index("navDate", inplace=True)
    df.sort_index(inplace=True)
    df["pct_change"] = df["nav"].pct_change()

    all_time_high_per_share = df["nav"].max()

    sortino = float(sortino_ratio(df["pct_change"], period="weekly"))
    if np.isnan(sortino) or np.isinf(sortino):
        sortino = 0
    downside = float(downside_risk(df["pct_change"], period="weekly"))
    if np.isnan(downside) or np.isinf(downside):
        downside = 0
    returns = df["pct_change"].values.flatten()
    risk_factor = calculate_risk_factor(returns)
    return all_time_high_per_share, sortino, downside, risk_factor


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


def get_total_shares(vault_contract: Contract, decimals=1e18):
    pps = vault_contract.functions.totalShares().call()
    return pps / decimals


def calculate_performance(
    vault_id: uuid.UUID,
    vault_contract: Contract,
    owner_address: str,
    update_freq: str = "daily",
):
    current_price = get_price("BTCUSDT")
    current_price_per_share = get_current_pps(vault_contract, decimals=1e8)
    total_balance = get_current_tvl(vault_contract, decimals=1e8)
    fee_info = get_fee_info()
    total_shares = get_total_shares(vault_contract)

    # get performance
    df = solv_service.fetch_nav_data()
    if df is None:
        logger.info("Failed to fetch NAV data")
        return

    # Calculate the APYs
    apy_1m = solv_service.get_monthly_apy(df, column="adjustedNav")
    apy_1w = solv_service.get_weekly_apy(df)
    apy_ytd = 0

    performance_history = session.exec(
        select(VaultPerformance).order_by(VaultPerformance.datetime.asc()).limit(1)
    ).first()

    benchmark = current_price
    benchmark_percentage = 0
    if performance_history is not None:
        benchmark_percentage = ((benchmark / performance_history.benchmark) - 1) * 100

    apy_1m = apy_1m * 100
    apy_1w = apy_1w * 100
    apy_ytd = apy_ytd * 100

    all_time_high_per_share, sortino, downside, risk_factor = (
        calculate_pps_statistics_from_solv(df)
    )

    # count all portfolio of vault
    statement = (
        select(func.count())
        .select_from(UserPortfolio)
        .where(UserPortfolio.vault_id == vault_id)
    )
    count = session.scalar(statement)

    # Create a new VaultPerformance object
    performance = VaultPerformance(
        datetime=datetime.now(timezone.utc),
        total_locked_value=total_balance,
        benchmark=benchmark,
        pct_benchmark=benchmark_percentage,
        apy_1m=apy_1m,
        apy_1w=apy_1w,
        apy_ytd=apy_ytd,
        vault_id=vault_id,
        risk_factor=risk_factor,
        all_time_high_per_share=all_time_high_per_share,
        total_shares=total_shares,
        sortino_ratio=sortino,
        downside_risk=downside,
        unique_depositors=count,
        earned_fee=0,
        fee_structure=fee_info,
    )
    update_price_per_share(vault_id, current_price_per_share)

    return performance


def main():
    try:

        # Get the vault from the Vault table with name = "Delta Neutral Vault"
        vaults = session.exec(
            select(Vault).where(Vault.slug == "arbitrum-wbtc-vault")
            # .where(Vault.is_active == True)
        ).all()
        logger.info("Start updating solv performance...")

        for vault in vaults:
            vault_contract, _ = get_vault_contract(vault, abi_name="solv")

            new_performance_rec = calculate_performance(
                vault.id,
                vault_contract,
                vault.owner_wallet_address,
                update_freq="daily",
            )
            # Add the new performance record to the session and commit
            session.add(new_performance_rec)

            # Update the vault with the new information
            vault.tvl = new_performance_rec.total_locked_value
            vault.ytd_apy = new_performance_rec.apy_ytd
            vault.monthly_apy = new_performance_rec.apy_1m
            vault.weekly_apy = new_performance_rec.apy_1w
            vault.next_close_round_date = None

            session.commit()
    except Exception as e:
        logger.error(
            "An error occurred while updating delta neutral performance: %s",
            e,
            exc_info=True,
        )


if __name__ == "__main__":
    setup_logging_to_console(logger=logger)
    setup_logging_to_file(f"update_solv_vault_performance", logger=logger)
    main()
