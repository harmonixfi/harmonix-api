import logging
from datetime import datetime, timedelta, timezone
from typing import List
import pandas as pd
from sqlmodel import Session


from bg_tasks.update_yield_vault_performance_init import (
    AE_USD,
    ALLOCATION_RATIO,
    LST_YEILD,
    RENZO_AEVO_VALUE,
    insert_vault_performance_history,
)
from log import setup_logging_to_console, setup_logging_to_file
from core.db import engine
from core import constants
from sqlmodel import Session, select

from models.vaults import Vault
from schemas.funding_history_entry import FundingHistoryEntry
from services import (
    aevo_service,
    bsx_service,
    gold_link_service,
    hyperliquid_service,
    lido_service,
    pendle_service,
    renzo_service,
)
from services.vault_performance_history_service import VaultPerformanceHistoryService
from utils.vault_utils import convert_to_nanoseconds, datetime_to_unix_ms


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

session = Session(engine)


def calculate_average_funding_rate_goldlink_vault(
    funding_histories: List[FundingHistoryEntry], target_date: datetime
):
    df = pd.DataFrame([fh.__dict__ for fh in funding_histories])

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

    # Filter data for the specific date
    filtered_df = df[df["datetime"].dt.date == target_date.date()]

    # Calculate the average funding rate
    average_rate = filtered_df["funding_rate"].mean() if not filtered_df.empty else 0

    return average_rate


def calculate_average_funding_rate(funding_histories: List[FundingHistoryEntry]):
    funding_rates = [entry.funding_rate for entry in funding_histories]
    average_rate = sum(funding_rates) / len(funding_rates) if funding_rates else 0
    return average_rate


def process_vault(
    vault: Vault, service: VaultPerformanceHistoryService, current_time: datetime
):
    handlers = {
        constants.KELPDAO_VAULT_SLUG: handle_vault_funding_with_aevo,
        constants.KELPDAO_GAIN_VAULT_SLUG: handle_vault_funding_with_aevo,
        constants.DELTA_NEUTRAL_VAULT_VAULT_SLUG: handle_vault_funding_with_aevo,
        constants.KELPDAO_VAULT_ARBITRUM_SLUG: handle_vault_funding_with_aevo,
        constants.BSX_VAULT_SLUG: handle_bsx_vault,
        constants.PENDLE_VAULT_VAULT_SLUG: handle_pendle_vault,
        constants.PENDLE_VAULT_VAULT_SLUG_DEC: handle_pendle_vault,
        constants.RENZO_VAULT_SLUG: handle_renzo_vault,
        constants.GOLD_LINK_SLUG: handle_goldlink_vault,
    }

    handler = handlers.get(vault.slug)
    if handler:
        handler(vault, service, current_time)
    else:
        logger.warning(f"Vault {vault.name} not supported")


def get_prev_tvl(vault: Vault, service: VaultPerformanceHistoryService):
    vault_performance = service.get_last_vault_performance(vault.id)
    if not vault_performance:
        error_message = f"No vault performance history found for vault {vault.name} (id: {vault.id})"
        logger.error(error_message)
        raise ValueError(error_message)
    return float(vault_performance.total_locked_value)


def handle_goldlink_vault(
    vault: Vault, service: VaultPerformanceHistoryService, current_time: datetime
):
    logger.info(f"Processing Goldlink vault: {vault.name}")
    prev_tvl = get_prev_tvl(vault, service)

    prev_date = current_time + timedelta(days=-1)
    funding_histories = gold_link_service.get_funding_history()
    # The funding rate of Goldlink is paid every 8 hours and is annualized
    funding_history = calculate_average_funding_rate_goldlink_vault(
        funding_histories, prev_date
    )
    funding_history_avg = funding_history / 365
    funding_value = funding_history_avg * 24 * prev_tvl
    yield_data = funding_value

    logger.info(f"Goldlink vault {vault.name} - Yield data calculated: {yield_data}")

    insert_vault_performance_history(
        yield_data=yield_data, vault=vault, datetime=current_time, service=service
    )


def handle_renzo_vault(
    vault: Vault, service: VaultPerformanceHistoryService, current_time: datetime
):
    logger.info(f"Processing Renzo vault: {vault.name}")
    prev_tvl = get_prev_tvl(vault, service)

    prev_date = current_time + timedelta(days=-1)
    funding_histories = aevo_service.get_funding_history(
        start_time=convert_to_nanoseconds(prev_date),
        end_time=convert_to_nanoseconds(
            prev_date.replace(hour=23, minute=59, second=59)
        ),
    )
    funding_history = calculate_average_funding_rate(funding_histories)
    renzo_apy = renzo_service.get_apy() / 100
    renzo_apy = renzo_apy / 365

    funding_value = funding_history * ALLOCATION_RATIO * 24 * prev_tvl
    ae_usd_value = RENZO_AEVO_VALUE * ALLOCATION_RATIO * prev_tvl
    ez_eth_value = renzo_apy * ALLOCATION_RATIO * prev_tvl
    yield_data = funding_value + ae_usd_value + ez_eth_value

    logger.info(f"Renzo vault {vault.name} - Yield data calculated: {yield_data}")

    insert_vault_performance_history(
        yield_data=yield_data, vault=vault, datetime=current_time, service=service
    )


def handle_pendle_vault(
    vault: Vault, service: VaultPerformanceHistoryService, current_time: datetime
):
    logger.info(f"Processing Pendle vault: {vault.name}")
    prev_tvl = get_prev_tvl(vault, service)

    prev_date = current_time + timedelta(days=-1)
    funding_histories = hyperliquid_service.get_funding_history(
        start_time=datetime_to_unix_ms(prev_date),
        end_time=datetime_to_unix_ms(prev_date.replace(hour=23, minute=59, second=59)),
    )
    funding_history = calculate_average_funding_rate(funding_histories)
    pendle_data = pendle_service.get_market(
        constants.CHAIN_IDS["CHAIN_ARBITRUM"], vault.pt_address
    )
    implied_apy = pendle_data[0].implied_apy if pendle_data else 0
    implied_apy = implied_apy / 365

    funding_value = funding_history * ALLOCATION_RATIO * 24 * prev_tvl
    fixed_value = implied_apy * prev_tvl * ALLOCATION_RATIO
    yield_data = funding_value + fixed_value

    logger.info(f"Pendle vault {vault.name} - Yield data calculated: {yield_data}")

    insert_vault_performance_history(
        yield_data=yield_data, vault=vault, datetime=current_time, service=service
    )


def handle_bsx_vault(
    vault: Vault, service: VaultPerformanceHistoryService, current_time: datetime
):
    logger.info(f"Processing BSX vault: {vault.name}")
    prev_tvl = get_prev_tvl(vault, service)

    prev_date = current_time + timedelta(days=-1)
    funding_histories = bsx_service.get_funding_history(
        start_time=convert_to_nanoseconds(prev_date),
        end_time=convert_to_nanoseconds(
            prev_date.replace(hour=23, minute=59, second=59)
        ),
    )
    funding_history = calculate_average_funding_rate(funding_histories)
    apy = lido_service.get_apy()
    apy = apy / 365

    funding_value = funding_history * ALLOCATION_RATIO * 24 * prev_tvl
    wst_eth_value_adjusted = apy * ALLOCATION_RATIO * prev_tvl
    yield_data = funding_value + wst_eth_value_adjusted

    logger.info(f"BSX vault {vault.name} - Yield data calculated: {yield_data}")

    insert_vault_performance_history(
        yield_data=yield_data, vault=vault, datetime=current_time, service=service
    )


def handle_vault_funding_with_aevo(
    vault: Vault, service: VaultPerformanceHistoryService, current_time: datetime
):
    logger.info(f"Processing vault funding with AEVO: {vault.name}")
    prev_tvl = get_prev_tvl(vault, service)

    prev_date = current_time + timedelta(days=-1)
    funding_histories = aevo_service.get_funding_history(
        start_time=convert_to_nanoseconds(prev_date),
        end_time=convert_to_nanoseconds(
            prev_date.replace(hour=23, minute=59, second=59)
        ),
    )
    funding_history = calculate_average_funding_rate(funding_histories)

    funding_value = funding_history * ALLOCATION_RATIO * 24 * prev_tvl
    ae_usd_value = AE_USD * ALLOCATION_RATIO * prev_tvl
    lst_yield_value = LST_YEILD * ALLOCATION_RATIO * prev_tvl
    yield_data = funding_value + ae_usd_value + lst_yield_value

    logger.info(f"AEVO vault {vault.name} - Yield data calculated: {yield_data}")

    insert_vault_performance_history(
        yield_data=yield_data, vault=vault, datetime=current_time, service=service
    )


def daily_yield_calculation():
    logger.info("Starting daily yield calculation...")

    service = VaultPerformanceHistoryService(session)
    vaults = service.get_active_vaults()
    try:
        service = VaultPerformanceHistoryService(session=session)
        datetimeNow = datetime.now(tz=timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        for vault in vaults:
            try:
                process_vault(vault, service, datetimeNow)
            except Exception as vault_error:
                logger.error(
                    f"An error occurred while processing vault {vault.name}: {vault_error}",
                    exc_info=True,
                )
    except Exception as e:
        logger.error(
            "An error occurred during daily yield calculation: %s", e, exc_info=True
        )


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file(f"update_yield_vault_performance_daily", logger=logger)
    daily_yield_calculation()
