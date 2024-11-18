from datetime import datetime, timedelta, timezone
import logging
from typing import List, Optional
import uuid

import pandas as pd
from sqlalchemy import func
from sqlmodel import Session, select
from web3 import Web3
from web3.contract import Contract

from core.abi_reader import read_abi
from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models import Vault
from core import constants
from models.point_distribution_history import PointDistributionHistory
from models.vault_apy_breakdown import VaultAPYBreakdown
from models.vault_performance import VaultPerformance
from models.vault_reward_history import VaultRewardHistory
from models.vaults import VaultMetadata


from schemas.funding_history_entry import FundingHistoryEntry
from services import lido_service, pendle_service, renzo_service
from services.gold_link_service import get_current_rewards_earned
from services.market_data import get_price
from services.vault_performance_history_service import VaultPerformanceHistoryService

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("calculate_apy_breakdown_daily")

session = Session(engine)

ALLOCATION_RATIO: float = 1 / 2
AE_USD = 0.08 / 365
LST_YEILD = 0.036 / 365
RENZO_AEVO_VALUE: float = 6.5 / 365


def get_funding_history(
    funding_histories: List[FundingHistoryEntry], datetime_str: str
) -> float:
    target_datetime = datetime.fromisoformat(datetime_str)

    for entry in funding_histories:
        if entry.datetime == target_datetime:
            return entry.funding_rate

    return 0


def get_vault_performance(vault_id) -> List[VaultPerformance]:
    return session.exec(
        select(VaultPerformance)
        .where(VaultPerformance.vault_id == vault_id)
        .order_by(VaultPerformance.datetime.asc())
    ).all()


def convert_datetime_from_df(daily_df: pd.DataFrame, index: int):
    return datetime.strptime(daily_df.iloc[index]["datetime"], "%Y-%m-%d").replace(
        tzinfo=timezone.utc
    )


def get_tvl_from_df(daily_df: pd.DataFrame, index: int) -> float:
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
    df.set_index("datetime", inplace=True)
    daily_df = df.resample("D").first()
    daily_df.ffill(inplace=True)
    daily_df.reset_index(inplace=True)
    daily_df["datetime"] = daily_df["datetime"].dt.strftime("%Y-%m-%d")
    return daily_df


def parse_to_funding_history(df: pd.DataFrame) -> List[FundingHistoryEntry]:
    return [
        FundingHistoryEntry(
            datetime=row["datetime"], funding_rate=row["funding_history"]
        )
        for _, row in df.iterrows()
    ]


def fetch_vaults():
    return session.exec(
        select(Vault).where(Vault.id != "ce16363b-57c5-4d64-9cf2-6e66b489baf0")
    ).all()


def process_vault(vault: Vault, service: VaultPerformanceHistoryService):
    if vault.slug == constants.KEYDAO_VAULT_ARBITRUM_SLUG:
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
    funding_histories, funding_histories_aevo = load_funding_histories()
    daily_df = get_vault_dataframe(vault)
    for i, row in daily_df.iterrows():
        if i == 0:
            continue
        dt = convert_datetime_from_df(daily_df, i)
        total_locked_value = get_tvl_from_df(daily_df, i - 1)

        date_move_vault = datetime(2024, 11, 11, tzinfo=timezone.utc)
        funding_history = get_funding_history(
            funding_histories_aevo, daily_df.iloc[i]["datetime"]
        )
        if dt >= date_move_vault:
            funding_history = get_funding_history(
                funding_histories, daily_df.iloc[i]["datetime"]
            )
        funding_value = funding_history * ALLOCATION_RATIO * 24 * total_locked_value
        AE_USD_value = AE_USD * ALLOCATION_RATIO * total_locked_value
        LST_YEILD_value = LST_YEILD * ALLOCATION_RATIO * total_locked_value
        yield_data = funding_value + AE_USD_value + LST_YEILD_value

        insert_vault_performance_history(
            yield_data=yield_data, vault=vault, datetime=dt, service=service
        )
    logger.info("Done process_kelpdao_arbtrum_vault")


def process_kelpdao_vault(vault: Vault, service: VaultPerformanceHistoryService):
    logger.info("Start process_kelpdao_vault")
    funding_histories = parse_to_funding_history(
        pd.read_csv("./data/funding_history_aevo.csv")
    )
    daily_df = get_vault_dataframe(vault)

    for i, row in daily_df.iterrows():
        if i == 0:
            continue
        dt = convert_datetime_from_df(daily_df, i)
        total_locked_value = get_tvl_from_df(daily_df, i - 1)
        funding_history = get_funding_history(
            funding_histories, daily_df.iloc[i]["datetime"]
        )

        funding_value = funding_history * ALLOCATION_RATIO * 24 * total_locked_value
        AE_USD_value = AE_USD * ALLOCATION_RATIO * total_locked_value
        LST_YEILD_value = LST_YEILD * ALLOCATION_RATIO * total_locked_value
        yield_data = funding_value + AE_USD_value + LST_YEILD_value

        insert_vault_performance_history(
            yield_data=yield_data, vault=vault, datetime=dt, service=service
        )
    logger.info("Done process_kelpdao_vault")


def process_bsx_vault(vault: Vault, service: VaultPerformanceHistoryService):
    logger.info("Start process_bsx_vault")
    funding_histories = parse_to_funding_history(
        pd.read_csv("./data/funding_history_bsx.csv")
    )
    wst_eth_value = lido_service.get_apy()
    daily_df = get_vault_dataframe(vault)
    for i, row in daily_df.iterrows():
        if i == 0:
            continue
        dt = convert_datetime_from_df(daily_df, i)
        total_locked_value = get_tvl_from_df(daily_df, i - 1)
        funding_history = get_funding_history(
            funding_histories, daily_df.iloc[i]["datetime"]
        )

        funding_value = funding_history * ALLOCATION_RATIO * 24 * total_locked_value
        wst_eth_value_adjusted = wst_eth_value * ALLOCATION_RATIO * total_locked_value
        yield_data = funding_value + wst_eth_value_adjusted
        insert_vault_performance_history(
            yield_data=yield_data, vault=vault, datetime=dt, service=service
        )

    logger.info("Done process_bsx_vault")


def process_pendle_vault(vault: Vault, service: VaultPerformanceHistoryService):
    logger.info("Start process_pendle_vault")
    pendle_data = pendle_service.get_market(
        constants.CHAIN_IDS["CHAIN_ARBITRUM"], vault.pt_address
    )
    fixed_value = pendle_data[0].implied_apy if pendle_data else 0
    funding_histories = parse_to_funding_history(
        pd.read_csv("./data/funding_history_hyperliquid.csv")
    )
    daily_df = get_vault_dataframe(vault)
    for i, row in daily_df.iterrows():
        if i == 0:
            continue
        dt = convert_datetime_from_df(daily_df, i)
        total_locked_value = get_tvl_from_df(daily_df, i - 1)
        funding_history = get_funding_history(
            funding_histories, daily_df.iloc[i]["datetime"]
        )
        funding_value = funding_history * ALLOCATION_RATIO * 24 * total_locked_value
        fixed_value_data = fixed_value * total_locked_value * ALLOCATION_RATIO
        yield_data = funding_value + fixed_value_data

        insert_vault_performance_history(
            yield_data=yield_data, vault=vault, datetime=dt, service=service
        )

    logger.info("Done process_pendle_vault")


def process_renzo_vault(vault: Vault, service: VaultPerformanceHistoryService):
    logger.info("Start process_renzo_vault")

    funding_histories = parse_to_funding_history(
        pd.read_csv("./data/funding_history_aevo.csv")
    )
    ez_eth_data = renzo_service.get_apy()
    daily_df = get_vault_dataframe(vault)

    for i, row in daily_df.iterrows():
        if i == 0:
            continue
        dt = convert_datetime_from_df(daily_df, i)
        total_locked_value = get_tvl_from_df(daily_df, i - 1)
        funding_history = get_funding_history(
            funding_histories, daily_df.iloc[i]["datetime"]
        )
        funding_value = funding_history * ALLOCATION_RATIO * 24 * total_locked_value
        ae_usd_value = RENZO_AEVO_VALUE * ALLOCATION_RATIO * total_locked_value
        ez_eth_value = ez_eth_data * ALLOCATION_RATIO * total_locked_value
        yield_data = funding_value + ae_usd_value + ez_eth_value

        insert_vault_performance_history(
            yield_data=yield_data, vault=vault, datetime=dt, service=service
        )
    logger.info("Done process_renzo_vault")


def process_goldlink_vault(vault: Vault, service: VaultPerformanceHistoryService):
    logger.info("Start process_goldlink_vault")
    funding_histories = parse_to_funding_history(
        pd.read_csv("./data/funding_history_goldlink.csv")
    )
    daily_df = get_vault_dataframe(vault)

    for i, row in daily_df.iterrows():
        if i == 0:
            continue
        dt = convert_datetime_from_df(daily_df, i)
        total_locked_value = get_tvl_from_df(daily_df, i - 1)
        funding_history = get_funding_history(
            funding_histories, daily_df.iloc[i]["datetime"]
        )
        funding_value = funding_history * ALLOCATION_RATIO * 24 * total_locked_value
        yield_data = funding_value

        insert_vault_performance_history(
            yield_data=yield_data, vault=vault, datetime=dt, service=service
        )

    logger.info("Done process_goldlink_vault")


def load_funding_histories():
    hyperliquid_df = pd.read_csv("./data/funding_history_hyperliquid.csv")
    aevo_df = pd.read_csv("./data/funding_history_aevo.csv")
    return parse_to_funding_history(hyperliquid_df), parse_to_funding_history(aevo_df)


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
        logger.info("Start calculating APY breakdown daily for vaults...")
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
            "An error occurred during APY breakdown calculation: %s", e, exc_info=True
        )


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file("update_yield_vault_performance_init", logger=logger)
    main()
