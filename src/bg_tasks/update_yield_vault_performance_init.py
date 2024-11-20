from datetime import datetime, timezone
import logging
from typing import List

import pandas as pd
from sqlmodel import Session, select

from bg_tasks.fetch_funding_history import CSV_PATH
from core.abi_reader import read_abi
from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models import Vault
from core import constants
from models.vault_performance import VaultPerformance
from services import lido_service, pendle_service, renzo_service

from services.vault_performance_history_service import VaultPerformanceHistoryService

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("calculate_apy_breakdown_daily")

session = Session(engine)

ALLOCATION_RATIO: float = 1 / 2
AE_USD = 0.08 / 365
LST_YEILD = 0.036 / 365
RENZO_AEVO_VALUE: float = 6.5 / 365


def get_daily_funding_rate_df(file_path: str):
    df = pd.read_csv(file_path)

    # Convert 'datetime' to UTC and normalize to the start of the day
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")

    # Handle invalid or missing datetime values
    if df["datetime"].isna().any():
        raise ValueError("Invalid datetime format detected in the 'datetime' column")

    # Ensure all datetimes are in UTC
    if df["datetime"].dt.tz is None:
        df["datetime"] = df["datetime"].dt.tz_localize("UTC")
    else:
        df["datetime"] = df["datetime"].dt.tz_convert("UTC")

    # Normalize to the start of the day
    df["date"] = df["datetime"].dt.floor("D")

    # Group by 'date' and calculate the average funding rate
    daily_avg = df.groupby("date")["funding_rate"].mean().reset_index()

    # Rename column to make it more descriptive
    daily_avg.rename(columns={"funding_rate": "average_funding_rate"}, inplace=True)
    return daily_avg


def get_funding_history(
    funding_histories_avg_df: pd.DataFrame, target_datetime: datetime
) -> float:
    filtered_row = funding_histories_avg_df.loc[
        funding_histories_avg_df["date"] == target_datetime
    ]
    if not filtered_row.empty:
        return filtered_row.iloc[0]["average_funding_rate"]
    return 0


def get_vault_performance(vault_id) -> List[VaultPerformance]:
    return session.exec(
        select(VaultPerformance)
        .where(VaultPerformance.vault_id == vault_id)
        .order_by(VaultPerformance.datetime.asc())
    ).all()


def get_tvl_from_prev_date(daily_df: pd.DataFrame, index: int) -> float:
    return float(daily_df.iloc[index]["total_locked_value"])


def convert_to_dataframe(vault_performance: List[VaultPerformance]):
    df = pd.DataFrame(
        [
            {
                "datetime": vp.datetime,
                "total_locked_value": vp.total_locked_value,
            }
            for vp in vault_performance
        ]
    )
    df["datetime"] = pd.to_datetime(df["datetime"])
    if df["datetime"].dt.tz is None:
        df["datetime"] = df["datetime"].dt.tz_localize("UTC")
    else:
        df["datetime"] = df["datetime"].dt.tz_convert("UTC")

    df["datetime"] = df["datetime"].dt.floor("D")
    df.set_index("datetime", inplace=True)

    daily_df = df.resample("D").first()
    daily_df.ffill(inplace=True)
    daily_df.reset_index(inplace=True)

    # Do not convert datetime to string here
    return daily_df


def fetch_vaults():
    # Ignore vault Koi & Chill with Kelp DAO with slug 'ethereum-kelpdao-restaking-delta-neutral-vault'
    return session.exec(
        select(Vault).where(Vault.id != "ce16363b-57c5-4d64-9cf2-6e66b489baf0")
    ).all()


def process_vault(vault: Vault, service: VaultPerformanceHistoryService):
    if vault.slug == constants.KELPDAO_VAULT_ARBITRUM_SLUG:
        process_kelpdao_arbtrum_vault(vault, service)
    elif vault.slug in {
        constants.KELPDAO_VAULT_SLUG,
        constants.KELPDAO_GAIN_VAULT_SLUG,
        constants.DELTA_NEUTRAL_VAULT_VAULT_SLUG,
    }:
        process_kelpdao_vault(vault, service)
    elif vault.slug == constants.BSX_VAULT_SLUG:
        process_bsx_vault(vault, service)
    elif vault.slug in {
        constants.PENDLE_VAULT_VAULT_SLUG,
        constants.PENDLE_VAULT_VAULT_SLUG_DEC,
    }:
        process_pendle_vault(vault, service)
    elif vault.slug == constants.RENZO_VAULT_SLUG:
        process_renzo_vault(vault, service)
    elif vault.slug == constants.GOLD_LINK_SLUG:
        process_goldlink_vault(vault, service)
    else:
        logger.warning(f"Vault {vault.name} not supported")


def process_kelpdao_arbtrum_vault(
    vault: Vault, service: VaultPerformanceHistoryService
):
    logger.info("Start process_kelpdao_arbtrum_vault")
    hyperliquid_funding_history_df = get_daily_funding_rate_df(CSV_PATH["HYPERLIQUID"])
    aevo_funding_history_df = get_daily_funding_rate_df(CSV_PATH["AEVO"])
    daily_df = get_vault_dataframe(vault)
    for i, row in daily_df.iterrows():
        if i == 0:
            continue
        date = row["datetime"]
        prev_tvl = get_tvl_from_prev_date(daily_df, i - 1)

        # From date: November 11, 2024 switched to Hyperliquid
        date_move_vault = datetime(2024, 11, 11, tzinfo=timezone.utc)
        funding_history = (
            get_funding_history(hyperliquid_funding_history_df, date)
            if date >= date_move_vault
            else get_funding_history(aevo_funding_history_df, date)
        )

        funding_value = funding_history * ALLOCATION_RATIO * 24 * prev_tvl
        ae_usd_value = AE_USD * ALLOCATION_RATIO * prev_tvl
        lst_yield_value = LST_YEILD * ALLOCATION_RATIO * prev_tvl
        yield_data = funding_value + ae_usd_value + lst_yield_value

        insert_vault_performance_history(
            yield_data=yield_data, vault=vault, datetime=date, service=service
        )
    logger.info("Done process_kelpdao_arbtrum_vault")


def process_kelpdao_vault(vault: Vault, service: VaultPerformanceHistoryService):
    logger.info("Start process_kelpdao_vault")
    aevo_funding_history_df = get_daily_funding_rate_df(CSV_PATH["AEVO"])
    daily_df = get_vault_dataframe(vault)

    for i, row in daily_df.iterrows():
        if i == 0:
            continue

        date = row["datetime"]
        prev_tvl = get_tvl_from_prev_date(daily_df, i - 1)
        funding_history = get_funding_history(aevo_funding_history_df, date)

        funding_value = funding_history * ALLOCATION_RATIO * 24 * prev_tvl
        AE_USD_value = AE_USD * ALLOCATION_RATIO * prev_tvl
        LST_YEILD_value = LST_YEILD * ALLOCATION_RATIO * prev_tvl
        yield_data = funding_value + AE_USD_value + LST_YEILD_value

        insert_vault_performance_history(
            yield_data=yield_data, vault=vault, datetime=date, service=service
        )
    logger.info("Done process_kelpdao_vault")


def process_bsx_vault(vault: Vault, service: VaultPerformanceHistoryService):
    logger.info("Start process_bsx_vault")
    bsx_funding_historiy_df = get_daily_funding_rate_df(CSV_PATH["BSX"])
    wst_eth_value = lido_service.get_apy()
    daily_df = get_vault_dataframe(vault)
    for i, row in daily_df.iterrows():
        if i == 0:
            continue
        date = row["datetime"]
        prev_tvl = get_tvl_from_prev_date(daily_df, i - 1)
        funding_history = get_funding_history(bsx_funding_historiy_df, date)

        funding_value = funding_history * ALLOCATION_RATIO * 24 * prev_tvl
        wst_eth_value_adjusted = wst_eth_value * ALLOCATION_RATIO * prev_tvl
        yield_data = funding_value + wst_eth_value_adjusted
        insert_vault_performance_history(
            yield_data=yield_data, vault=vault, datetime=date, service=service
        )

    logger.info("Done process_bsx_vault")


def process_pendle_vault(vault: Vault, service: VaultPerformanceHistoryService):
    logger.info("Start process_pendle_vault")
    pendle_data = pendle_service.get_market(
        constants.CHAIN_IDS["CHAIN_ARBITRUM"], vault.pt_address
    )
    fixed_value = pendle_data[0].implied_apy if pendle_data else 0
    hyperliquid_funding_history_df = get_daily_funding_rate_df(CSV_PATH["HYPERLIQUID"])
    daily_df = get_vault_dataframe(vault)
    for i, row in daily_df.iterrows():
        if i == 0:
            continue
        date = row["datetime"]
        prev_tvl = get_tvl_from_prev_date(daily_df, i - 1)
        funding_history = get_funding_history(hyperliquid_funding_history_df, date)
        funding_value = funding_history * ALLOCATION_RATIO * 24 * prev_tvl
        fixed_value_data = fixed_value * prev_tvl * ALLOCATION_RATIO
        yield_data = funding_value + fixed_value_data

        insert_vault_performance_history(
            yield_data=yield_data, vault=vault, datetime=date, service=service
        )

    logger.info("Done process_pendle_vault")


def process_renzo_vault(vault: Vault, service: VaultPerformanceHistoryService):
    logger.info("Start process_renzo_vault")

    aevo_funding_history_df = get_daily_funding_rate_df(CSV_PATH["AEVO"])
    ez_eth_data = renzo_service.get_apy()
    daily_df = get_vault_dataframe(vault)

    for i, row in daily_df.iterrows():
        if i == 0:
            continue

        date = row["datetime"]
        prev_tvl = get_tvl_from_prev_date(daily_df, i - 1)
        funding_history = get_funding_history(aevo_funding_history_df, date)
        funding_value = funding_history * ALLOCATION_RATIO * 24 * prev_tvl
        ae_usd_value = RENZO_AEVO_VALUE * ALLOCATION_RATIO * prev_tvl
        ez_eth_value = ez_eth_data * ALLOCATION_RATIO * prev_tvl
        yield_data = funding_value + ae_usd_value + ez_eth_value

        insert_vault_performance_history(
            yield_data=yield_data, vault=vault, datetime=date, service=service
        )
    logger.info("Done process_renzo_vault")


def process_goldlink_vault(vault: Vault, service: VaultPerformanceHistoryService):
    logger.info("Start process_goldlink_vault")
    goldlink_funding_history_df = get_daily_funding_rate_df(CSV_PATH["GOLDLINK"])
    daily_df = get_vault_dataframe(vault)

    for i, row in daily_df.iterrows():
        if i == 0:
            continue

        date = row["datetime"]
        prev_tvl = get_tvl_from_prev_date(daily_df, i - 1)
        funding_history = get_funding_history(goldlink_funding_history_df, date)
        funding_value = funding_history * ALLOCATION_RATIO * 24 * prev_tvl
        yield_data = funding_value

        insert_vault_performance_history(
            yield_data=yield_data, vault=vault, datetime=date, service=service
        )

    logger.info("Done process_goldlink_vault")


def get_vault_dataframe(vault: Vault):
    vault_performance = get_vault_performance(vault_id=vault.id)
    return convert_to_dataframe(vault_performance=vault_performance)


def insert_vault_performance_history(
    vault: Vault,
    yield_data: float,
    datetime: datetime,
    service: VaultPerformanceHistoryService,
):
    if (
        vault.update_frequency == constants.UpdateFrequency.weekly.value
        and datetime.weekday() != 4
    ):
        yield_data = 0

    service.insert_vault_performance_history(
        yield_data=yield_data, vault_id=vault.id, date=datetime
    )


# Main Execution
def main():
    try:
        logger.info("Start calculating yield of all vaults...")
        vaults = fetch_vaults()
        service = VaultPerformanceHistoryService(session=session)

        for vault in vaults:
            try:
                process_vault(vault, service)
            except Exception as vault_error:
                logger.error(
                    f"An error occurred while processing vault {vault.name}: {vault_error}",
                    exc_info=True,
                )
    except Exception as e:
        logger.error(
            "An error occurred during yield calculation for vaults: %s",
            e,
            exc_info=True,
        )


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file("update_yield_vault_performance_init", logger=logger)
    main()
