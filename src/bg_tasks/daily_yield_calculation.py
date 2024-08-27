import logging
from datetime import datetime
from sqlmodel import Session

from log import setup_logging_to_console, setup_logging_to_file
from core.db import engine
from core import constants
from sqlmodel import Session, select

from services.vault_performance_history_service import VaultPerformanceHistoryService
from utils.web3_utils import parse_hex_to_int


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

session = Session(engine)


def daily_yield_calculation():
    logger.info("Starting calculate day...")

    service = VaultPerformanceHistoryService(session)
    vaults = service.get_active_vaults()

    datetimeNow = datetime.now()
    for vault in vaults:
        if (
            vault.update_frequency == constants.UpdateFrequency.weekly.value
            and datetimeNow.weekday() == 4
        ):
            yield_data = service.process_vault_performance(vault, datetimeNow)

        elif (
            vault.update_frequency == constants.UpdateFrequency.weekly.value
            and datetimeNow.weekday() != 4
        ):
            yield_data = 0

        else:
            yield_data = service.process_vault_performance(vault, datetimeNow)

        service.insert_vault_performance_history(yield_data, vault.id, datetimeNow)


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file(f"calculate_yield_day", logger=logger)
    daily_yield_calculation()
