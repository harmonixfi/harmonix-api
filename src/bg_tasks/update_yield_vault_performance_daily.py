import logging
from datetime import datetime, timezone
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

from models.vault_performance import VaultPerformance
from models.vaults import Vault
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


def process_vault(
    vault: Vault, service: VaultPerformanceHistoryService, current_time: datetime
):
    handlers = {
        constants.KELPDAO_VAULT_SLUG: process_vault_to_aevo,
        constants.KELPDAO_GAIN_VAULT_SLUG: process_vault_to_aevo,
        constants.DELTA_NEUTRAL_VAULT_VAULT_SLUG: process_vault_to_aevo,
        constants.KEYDAO_VAULT_ARBITRUM_SLUG: process_vault_to_aevo,
        constants.BSX_VAULT_SLUG: process_vault_to_bsx,
        constants.PENDLE_VAULT_VAULT_SLUG: process_pendle_vault,
        constants.PENDLE_VAULT_VAULT_SLUG_DEC: process_pendle_vault,
        constants.RENZO_VAULT_SLUG: process_renzo_vault,
        constants.GOLD_LINK_SLUG: process_goldlink_vault,
    }

    handler = handlers.get(vault.slug)
    if handler:
        handler(vault, service, current_time)
    else:
        logger.warning(f"Vault {vault.name} not supported")


def get_vault_performance(
    vault: Vault, service: VaultPerformanceHistoryService, current_time: datetime
):
    vault_performances = service.get_vault_performances(vault.id, current_time)
    if not vault_performances:
        logger.error(
            f"No vault performance history found for vault {vault.name} (id: {vault.id}) at {current_time}"
        )
        return None
    return float(vault_performances[0].total_locked_value)


def calculate_yield_data(
    funding_history, allocation_ratio, total_locked_value, additional_values=None
):
    additional_values = additional_values or []
    funding_value = funding_history * allocation_ratio * 24 * total_locked_value
    return funding_value + sum(additional_values)


def process_goldlink_vault(
    vault: Vault, service: VaultPerformanceHistoryService, current_time: datetime
):
    total_locked_value = get_vault_performance(vault, service, current_time)
    if total_locked_value is None:
        return

    funding_history = 7
    yield_data = calculate_yield_data(
        funding_history, ALLOCATION_RATIO, total_locked_value
    )

    insert_vault_performance_history(
        yield_data=yield_data, vault=vault, datetime=current_time, service=service
    )


def process_renzo_vault(
    vault: Vault, service: VaultPerformanceHistoryService, current_time: datetime
):
    total_locked_value = get_vault_performance(vault, service, current_time)
    if total_locked_value is None:
        return

    funding_history = aevo_service.get_funding_history(
        start_time=convert_to_nanoseconds(current_time),
        end_time=convert_to_nanoseconds(
            current_time.replace(hour=23, minute=59, second=59)
        ),
    )
    ez_eth_data = renzo_service.get_apy()
    additional_values = [
        RENZO_AEVO_VALUE * ALLOCATION_RATIO * total_locked_value,
        ez_eth_data * ALLOCATION_RATIO * total_locked_value,
    ]
    yield_data = calculate_yield_data(
        funding_history, ALLOCATION_RATIO, total_locked_value, additional_values
    )

    insert_vault_performance_history(
        yield_data=yield_data, vault=vault, datetime=current_time, service=service
    )


def process_pendle_vault(
    vault: Vault, service: VaultPerformanceHistoryService, current_time: datetime
):
    total_locked_value = get_vault_performance(vault, service, current_time)
    if total_locked_value is None:
        return

    funding_history = hyperliquid_service.get_funding_history(
        start_time=datetime_to_unix_ms(current_time),
        end_time=datetime_to_unix_ms(
            current_time.replace(hour=23, minute=59, second=59)
        ),
    )
    pendle_data = pendle_service.get_market(
        constants.CHAIN_IDS["CHAIN_ARBITRUM"], vault.pt_address
    )
    fixed_value = pendle_data[0].implied_apy if pendle_data else 0
    additional_values = [fixed_value * total_locked_value * ALLOCATION_RATIO]
    yield_data = calculate_yield_data(
        funding_history, ALLOCATION_RATIO, total_locked_value, additional_values
    )

    insert_vault_performance_history(
        yield_data=yield_data, vault=vault, datetime=current_time, service=service
    )


def process_vault_to_bsx(
    vault: Vault, service: VaultPerformanceHistoryService, current_time: datetime
):
    total_locked_value = get_vault_performance(vault, service, current_time)
    if total_locked_value is None:
        return

    funding_history = bsx_service.get_funding_history(
        start_time=convert_to_nanoseconds(current_time),
        end_time=convert_to_nanoseconds(
            current_time.replace(hour=23, minute=59, second=59)
        ),
    )
    wst_eth_value = lido_service.get_apy()
    additional_values = [wst_eth_value * ALLOCATION_RATIO * total_locked_value]
    yield_data = calculate_yield_data(
        funding_history, ALLOCATION_RATIO, total_locked_value, additional_values
    )

    insert_vault_performance_history(
        yield_data=yield_data, vault=vault, datetime=current_time, service=service
    )


def process_vault_to_aevo(
    vault: Vault, service: VaultPerformanceHistoryService, current_time: datetime
):
    total_locked_value = get_vault_performance(vault, service, current_time)
    if total_locked_value is None:
        return

    funding_history = aevo_service.get_funding_history(
        start_time=convert_to_nanoseconds(current_time),
        end_time=convert_to_nanoseconds(
            current_time.replace(hour=23, minute=59, second=59)
        ),
    )
    additional_values = [
        AE_USD * ALLOCATION_RATIO * total_locked_value,
        LST_YEILD * ALLOCATION_RATIO * total_locked_value,
    ]
    yield_data = calculate_yield_data(
        funding_history, ALLOCATION_RATIO, total_locked_value, additional_values
    )

    insert_vault_performance_history(
        yield_data=yield_data, vault=vault, datetime=current_time, service=service
    )


def daily_yield_calculation():
    logger.info("Starting calculate day...")

    service = VaultPerformanceHistoryService(session)
    vaults = service.get_active_vaults()
    try:
        service = VaultPerformanceHistoryService(session=session)
        datetimeNow = datetime.now(tz=timezone.utc)
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
            "An error occurred during APY breakdown calculation: %s", e, exc_info=True
        )


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file(f"update_yield_vault_performance_daily", logger=logger)
    daily_yield_calculation()
