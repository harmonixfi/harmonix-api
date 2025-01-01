from datetime import datetime, timedelta, timezone
import logging
from typing import List
import pandas as pd
from sqlalchemy import func
from sqlmodel import Session, select
from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models import Vault
from core import constants
from models.funding_rate_history import FundingRateHistory
from models.goldlink_borrow_rate_history import GoldlinkBorrowRateHistory
from reports.ultils import (
    AE_USD,
    LEVERAGE,
    LST_YEILD,
    ALLOCATION_RATIO,
    PARTNER,
    RENZO_AEVO_VALUE,
)
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

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("calculate_apy_breakdown_daily")

session = Session(engine)


def calculate_average_funding_rate(partner_name: str):
    max_date_query = select(func.max(FundingRateHistory.datetime)).where(
        FundingRateHistory.partner_name == partner_name
    )
    max_date = session.exec(max_date_query).first()

    if max_date:
        query = (
            select(FundingRateHistory.funding_rate)
            .where(FundingRateHistory.partner_name == partner_name)
            .where(func.date(FundingRateHistory.datetime) == max_date.date())
        )
        data = session.exec(query).all()
        if data:
            return sum(data) / len(data)

    else:
        return 0


def get_prev_tvl(vault: Vault, service: VaultPerformanceHistoryService):
    vault_performance = service.get_last_vault_performance(vault.id)
    if not vault_performance:
        error_message = f"No vault performance history found for vault {vault.name} (id: {vault.id})"
        logger.error(error_message)
        raise ValueError(error_message)
    return float(vault_performance.total_locked_value)


def get_avg_interest_rate():
    max_date_query = select(func.max(GoldlinkBorrowRateHistory.datetime))
    max_date = session.exec(max_date_query).first()

    if max_date:
        query = select(GoldlinkBorrowRateHistory.apy_rate).where(
            func.date(GoldlinkBorrowRateHistory.datetime) == max_date.date()
        )
        data = session.exec(query).all()
        if data:
            return sum(data) / len(data)

    else:
        return 0


def fetch_vaults():
    # Ignore vault Koi & Chill with Kelp DAO with slug 'ethereum-kelpdao-restaking-delta-neutral-vault'
    return session.exec(
        select(Vault).where(Vault.id != "ce16363b-57c5-4d64-9cf2-6e66b489baf0")
    ).all()


def process_vault(
    vault: Vault, service: VaultPerformanceHistoryService, current_time: datetime
):
    handlers = {
        constants.KELPDAO_VAULT_ARBITRUM_SLUG: handle_vault_funding_with_aevo,
        constants.KELPDAO_VAULT_SLUG: handle_vault_funding_with_aevo,
        constants.KELPDAO_GAIN_VAULT_SLUG: handle_vault_funding_with_aevo,
        constants.DELTA_NEUTRAL_VAULT_VAULT_SLUG: handle_vault_funding_with_aevo,
        constants.BSX_VAULT_SLUG: handle_bsx_vault,
        constants.PENDLE_VAULT_VAULT_SLUG: handle_pendle_vault,
        constants.PENDLE_VAULT_VAULT_SLUG_DEC: handle_pendle_vault,
        constants.RENZO_VAULT_SLUG: handle_renzo_vault,
        constants.GOLD_LINK_SLUG: handle_goldlink_vault,
        constants.HYPE_DELTA_NEUTRAL_SLUG: handle_hype_vault,
    }

    handler = handlers.get(vault.slug)
    if handler:
        handler(vault, service, current_time)
    else:
        logger.warning(f"Vault {vault.name} not supported")


def handle_vault_funding_with_aevo(
    vault: Vault, service: VaultPerformanceHistoryService, current_time: datetime
):
    logger.info(f"Processing vault funding with AEVO: {vault.name}")
    prev_tvl = get_prev_tvl(vault, service)

    funding_avg_hourly = calculate_average_funding_rate(PARTNER["AEVO"])
    daily_funding_rate = funding_avg_hourly * 24

    funding_value = daily_funding_rate * ALLOCATION_RATIO * prev_tvl
    ae_usd_value = AE_USD * ALLOCATION_RATIO * prev_tvl
    lst_yield_value = LST_YEILD * ALLOCATION_RATIO * prev_tvl
    yield_data = funding_value + ae_usd_value + lst_yield_value

    logger.info(f"AEVO vault {vault.name} - Yield data calculated: {yield_data}")

    insert_vault_performance_history(
        yield_data=yield_data, vault=vault, datetime=current_time, service=service
    )


def handle_bsx_vault(
    vault: Vault, service: VaultPerformanceHistoryService, current_time: datetime
):
    logger.info(f"Processing BSX vault: {vault.name}")
    prev_tvl = get_prev_tvl(vault, service)

    lido_apy = lido_service.get_apy()
    lido_daily_apy = lido_apy / 365

    funding_avg_hourly = calculate_average_funding_rate(PARTNER["BSX"])
    daily_funding_rate = funding_avg_hourly * 24

    funding_value = daily_funding_rate * ALLOCATION_RATIO * prev_tvl
    wst_eth_value_adjusted = lido_daily_apy * ALLOCATION_RATIO * prev_tvl
    yield_data = funding_value + wst_eth_value_adjusted

    logger.info(f"BSX vault {vault.name} - Yield data calculated: {yield_data}")

    insert_vault_performance_history(
        yield_data=yield_data, vault=vault, datetime=current_time, service=service
    )


def handle_pendle_vault(
    vault: Vault, service: VaultPerformanceHistoryService, current_time: datetime
):
    logger.info(f"Processing Pendle vault: {vault.name}")
    pendle_data = pendle_service.get_market(
        constants.CHAIN_IDS["CHAIN_ARBITRUM"], vault.pt_address
    )
    pendle_fixed_apy = pendle_data[0].implied_apy if pendle_data else 0
    pendle_daily_apy = pendle_fixed_apy / 365

    prev_tvl = get_prev_tvl(vault, service)

    funding_avg_hourly = calculate_average_funding_rate(PARTNER["HYPERLIQUID"])
    daily_funding_rate = funding_avg_hourly * 24

    funding_value = daily_funding_rate * ALLOCATION_RATIO * prev_tvl
    fixed_value = pendle_daily_apy * ALLOCATION_RATIO * prev_tvl
    yield_data = funding_value + fixed_value

    logger.info(f"Pendle vault {vault.name} - Yield data calculated: {yield_data}")

    insert_vault_performance_history(
        yield_data=yield_data, vault=vault, datetime=current_time, service=service
    )

    logger.info("Done process_pendle_vault")


def handle_renzo_vault(
    vault: Vault, service: VaultPerformanceHistoryService, current_time: datetime
):
    logger.info(f"Processing Renzo vault: {vault.name}")
    renzo_apy = renzo_service.get_apy() / 100
    renzo_daily_apy = renzo_apy / 365

    prev_tvl = get_prev_tvl(vault, service)

    funding_avg_hourly = calculate_average_funding_rate(PARTNER["AEVO"])
    daily_funding_rate = funding_avg_hourly * 24

    funding_value = daily_funding_rate * ALLOCATION_RATIO * prev_tvl
    ae_usd_value = RENZO_AEVO_VALUE * ALLOCATION_RATIO * prev_tvl
    ez_eth_value = renzo_daily_apy * ALLOCATION_RATIO * prev_tvl
    yield_data = funding_value + ae_usd_value + ez_eth_value

    logger.info(f"Renzo vault {vault.name} - Yield data calculated: {yield_data}")

    insert_vault_performance_history(
        yield_data=yield_data, vault=vault, datetime=current_time, service=service
    )


def handle_goldlink_vault(
    vault: Vault, service: VaultPerformanceHistoryService, current_time: datetime
):
    logger.info(f"Processing Goldlink vault: {vault.name}")
    prev_tvl = get_prev_tvl(vault, service)
    prev_tvl = prev_tvl * LEVERAGE

    interest_rate = get_avg_interest_rate()
    # The funding rate of Goldlink is paid every 8 hours and is annualized
    funding_history = calculate_average_funding_rate(PARTNER["GOLDLINK"])
    # The funding rate of Goldlink is paid every 8 hours and is annualized
    funding_history_avg = float(funding_history) / 365
    interest_rate_avg = float(interest_rate) / 365
    # Calculate funding value based on the difference between the 1-day average funding rate
    # and the 1-day average interest rate, scaled by the TVL (Total Value Locked) and a multiplier of 4.
    # Formula: (Funding Rate Avg 1D - Interest Rate Avg 1D) * (TVL * 4)

    funding_value = (funding_history_avg - interest_rate_avg) * prev_tvl
    yield_data = funding_value

    logger.info(f"Goldlink vault {vault.name} - Yield data calculated: {yield_data}")

    insert_vault_performance_history(
        yield_data=yield_data, vault=vault, datetime=current_time, service=service
    )


def handle_hype_vault(
    vault: Vault, service: VaultPerformanceHistoryService, current_time: datetime
):
    logger.info(f"Processing hype vault: {vault.name}")

    prev_tvl = get_prev_tvl(vault, service)
    funding_avg_hourly = calculate_average_funding_rate(PARTNER["HYPERLIQUID_HYPE"])
    daily_funding_rate = funding_avg_hourly * 24
    funding_value = daily_funding_rate * ALLOCATION_RATIO * prev_tvl
    yield_data = funding_value

    logger.info(f"HYPE vault {vault.name} - Yield data calculated: {yield_data}")

    insert_vault_performance_history(
        yield_data=yield_data, vault=vault, datetime=current_time, service=service
    )

    logger.info("Done handle_hype_vault")


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
        datetime_now = datetime.now(tz=timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        for vault in vaults:
            try:
                process_vault(vault, service, datetime_now)
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
    setup_logging_to_file(
        "update_vault_earned_yield_historical_daily",
        logger=logger,
    )
    main()
