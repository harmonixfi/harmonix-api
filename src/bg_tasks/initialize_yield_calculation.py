import logging
from datetime import datetime, timedelta
from typing import List
from sqlmodel import Session, select

from log import setup_logging_to_console, setup_logging_to_file
from core.db import engine
from core import constants

from services.vault_performance_history_service import VaultPerformanceHistoryService
from utils.extension_utils import get_init_dates


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

session = Session(engine)


def initialize_yield_calculation():
    logger.info("Starting calculate Yield init...")

    service = VaultPerformanceHistoryService(session)
    vaults = service.get_active_vaults()

    vault_performance_dates = get_init_dates()

    for vault in vaults:
        yield_eth = {}
        for vault_performance_date in vault_performance_dates:
            
            if vault.update_frequency == constants.UpdateFrequency.weekly.value and vault_performance_date.weekday() == 4 :
                yield_data = service.process_vault_performance(
                    vault, vault_performance_date
                )
                
                yield_eth['yield'] = yield_data
                
            elif vault.update_frequency == constants.UpdateFrequency.weekly.value and vault_performance_date.weekday() != 4:
                yield_data = yield_eth['yield']
            
            else:
                yield_data = service.process_vault_performance(
                    vault, vault_performance_date
                )
                
            service.insert_vault_performance_history(
                    yield_data, vault.id, vault_performance_date
            )
                
                


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file(f"calculate_yield_day_init", logger=logger)
    initialize_yield_calculation()
