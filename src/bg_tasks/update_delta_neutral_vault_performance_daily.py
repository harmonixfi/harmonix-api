import logging
import uuid
from datetime import datetime, timedelta, timezone

import click
import pandas as pd
import pendulum
import seqlog
from sqlalchemy import func
from sqlmodel import Session, select
from web3 import Web3
from web3.contract import Contract

from bg_tasks.utils import (
    calculate_pps_statistics,
    calculate_roi,
    get_before_price_per_shares,
)
from core import constants
from core.abi_reader import read_abi
from core.config import settings
from core.db import engine
from models import Vault
from models.pps_history import PricePerShareHistory
from models.user_portfolio import UserPortfolio
from models.vault_performance import VaultPerformance
from models.vaults import NetworkChain
from schemas.fee_info import FeeInfo
from schemas.vault_state import VaultState
from services.market_data import get_price

if settings.SEQ_SERVER_URL is not None or settings.SEQ_SERVER_URL != "":
    seqlog.configure_from_file("./config/seqlog.yml")

# # Initialize logger
logger = logging.getLogger("update_delta_neutral_vault_performance_daily")
logger.setLevel(logging.INFO)

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


def get_current_pps(vault_contract: Contract):
    pps = vault_contract.functions.pricePerShare().call()
    return pps / 1e6


def get_current_tvl(vault_contract: Contract):
    tvl = vault_contract.functions.totalValueLocked().call()

    return tvl / 1e6


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
    vault_state = VaultState(
        withdraw_pool_amount=state[0] / 1e6,
        pending_deposit=state[1] / 1e6,
        total_share=state[2] / 1e6,
        total_fee_pool_amount=state[3] / 1e6,
        last_update_management_fee_date=state[4],
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


# Step 4: Calculate Performance Metrics
def calculate_performance(
    vault_id: uuid.UUID,
    vault_contract: Contract,
    owner_address: str,
    update_freq: str = "daily",
):
    current_price = get_price("ETHUSDT")

    # today = datetime.strptime(df["Date"].iloc[-1], "%Y-%m-%d")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    # candles = get_klines("ETHUSDT", end_time=(today + timedelta(days=2)), limit=1)
    # current_price = float(candles[0][4])

    # price_per_share_df = get_price_per_share_history(vault_id)

    current_price_per_share = get_current_pps(vault_contract)
    total_balance = get_current_tvl(vault_contract)
    fee_info = get_fee_info()
    vault_state = get_vault_state(vault_contract, owner_address=owner_address)
    # Calculate Monthly APY
    month_ago_price_per_share = get_before_price_per_shares(session, vault_id, days=30)
    month_ago_datetime = pendulum.instance(month_ago_price_per_share.datetime).in_tz(
        pendulum.UTC
    )

    time_diff = pendulum.now(tz=pendulum.UTC) - month_ago_datetime
    days = min((time_diff).days, 30) if time_diff.days > 0 else time_diff.hours / 24
    monthly_apy = calculate_roi(
        current_price_per_share, month_ago_price_per_share.price_per_share, days=days
    )

    week_ago_price_per_share = get_before_price_per_shares(session, vault_id, days=7)
    week_ago_datetime = pendulum.instance(week_ago_price_per_share.datetime).in_tz(
        pendulum.UTC
    )
    time_diff = pendulum.now(tz=pendulum.UTC) - week_ago_datetime
    days = min(time_diff.days, 7) if time_diff.days > 0 else time_diff.hours / 24
    weekly_apy = calculate_roi(
        current_price_per_share, week_ago_price_per_share.price_per_share, days=days
    )

    apy_ytd = calculate_apy_ytd(vault_id, current_price_per_share)

    performance_history = session.exec(
        select(VaultPerformance).order_by(VaultPerformance.datetime.asc()).limit(1)
    ).first()

    benchmark = current_price
    benchmark_percentage = ((benchmark / performance_history.benchmark) - 1) * 100
    apy_1m = monthly_apy * 100
    apy_1w = weekly_apy * 100
    apy_ytd = apy_ytd * 100

    # query last 7 days VaultPerformance
    if update_freq == "daily":
        last_7_day = datetime.now(timezone.utc) - timedelta(days=7)

        last_6_days = session.exec(
            select(VaultPerformance)
            .where(VaultPerformance.vault_id == vault_id)
            .where(VaultPerformance.datetime >= last_7_day)
            .order_by(VaultPerformance.datetime.desc())
        ).all()

        # convert last 6 days apy to dataframe
        last_6_days_df = pd.DataFrame([vars(rec) for rec in last_6_days])
        last_6_days_df = last_6_days_df[["datetime", "apy_1m", "apy_1w"]].copy()

        # append latest apy
        new_row = pd.DataFrame(
            [
                {
                    "datetime": today,
                    "apy_1m": apy_1m,
                    "apy_1w": apy_1w,
                }
            ]
        )
        new_row["datetime"] = pd.to_datetime(new_row["datetime"])
        last_6_days_df = pd.concat([last_6_days_df, new_row]).reset_index(drop=True)

        # resample last_6_days_df to daily frequency
        last_6_days_df["datetime"] = pd.to_datetime(last_6_days_df["datetime"])
        last_6_days_df.set_index("datetime", inplace=True)
        last_6_days_df = last_6_days_df.resample("D").mean()

        if len(last_6_days_df) >= 7:
            # calculate average 7 days apy_1m included today
            apy_1m = last_6_days_df.ffill()["apy_1m"].mean()
            apy_1w = last_6_days_df.ffill()["apy_1w"].mean()

    all_time_high_per_share, sortino, downside, risk_factor = calculate_pps_statistics(
        session, vault_id
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
        datetime=today,
        total_locked_value=total_balance,
        benchmark=benchmark,
        pct_benchmark=benchmark_percentage,
        apy_1m=apy_1m,
        apy_1w=apy_1w,
        apy_ytd=apy_ytd,
        vault_id=vault_id,
        risk_factor=risk_factor,
        all_time_high_per_share=all_time_high_per_share,
        total_shares=vault_state.total_share,
        sortino_ratio=sortino,
        downside_risk=downside,
        unique_depositors=count,
        earned_fee=vault_state.total_fee_pool_amount,
        fee_structure=fee_info,
    )
    update_price_per_share(vault_id, current_price_per_share)

    return performance


def get_vault_contract(vault: Vault) -> tuple[Contract, Web3]:
    w3 = Web3(Web3.HTTPProvider(constants.NETWORK_RPC_URLS[vault.network_chain]))

    rockonyx_delta_neutral_vault_abi = read_abi("RockOnyxDeltaNeutralVault")
    vault_contract = w3.eth.contract(
        address=vault.contract_address,
        abi=rockonyx_delta_neutral_vault_abi,
    )
    return vault_contract, w3


# Main Execution
@click.command()
@click.option("--chain", default="arbitrum_one", help="Blockchain network to use")
def main(chain: str):
    try:
        # Parse chain to NetworkChain enum
        network_chain = NetworkChain[chain.lower()]

        # Get the vault from the Vault table with name = "Delta Neutral Vault"
        vaults = session.exec(
            select(Vault)
            .where(Vault.strategy_name == constants.DELTA_NEUTRAL_STRATEGY)
            .where(Vault.is_active == True)
            .where(Vault.network_chain == network_chain)
        ).all()

        for vault in vaults:
            vault_contract, _ = get_vault_contract(vault)

            new_performance_rec = calculate_performance(
                vault.id,
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
            vault.next_close_round_date = None

            session.commit()
    except Exception as e:
        logger.error(
            "An error occurred while updating delta neutral performance: %s",
            e,
            exc_info=True,
        )


if __name__ == "__main__":
    main()
