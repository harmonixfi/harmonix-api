import logging
from datetime import datetime, timedelta
from typing import List
from sqlalchemy import text
from sqlmodel import Session, select

from log import setup_logging_to_console, setup_logging_to_file
from core.db import engine
from core import constants

from models.vault_performance import VaultPerformance
from models.vaults import Vault
from services.vault_performance_history_service import VaultPerformanceHistoryService


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

session = Session(engine)


def get_init_dates(vault: Vault) -> List[datetime]:
    raw_query = text(
        """
         SELECT MIN(datetime) AS datetime
            FROM public.vault_performance
        where vault_id =:vault_id
        """
    )

    # Execute the query and retrieve the result
    result = session.exec(raw_query.bindparams(vault_id=vault.id)).one()
    min_date = result.datetime
    # min_date = datetime(2024, 6, 13)
    end_date = datetime.now() - timedelta(days=1)

    date_list = []
    add_date = 1
    if vault.update_frequency == constants.UpdateFrequency.weekly.value:
        add_date = 7

    current_date = min_date + timedelta(days=add_date)

    while current_date <= end_date:
        date_list.append(current_date)
        current_date += timedelta(days=1)

    return date_list


def initialize_yield_calculation():
    logger.info("Starting calculate Yield init...")

    service = VaultPerformanceHistoryService(session)
    vaults = service.get_active_vaults()

    for vault in vaults:
        vault_performance_dates = get_init_dates(vault)
        for vault_performance_date in vault_performance_dates:

            if (
                vault.update_frequency == constants.UpdateFrequency.weekly.value
                and vault_performance_date.weekday() == 4
            ):
                yield_data = service.process_vault_performance(
                    vault, vault_performance_date
                )

            elif (
                vault.update_frequency == constants.UpdateFrequency.weekly.value
                and vault_performance_date.weekday() != 4
            ):
                yield_data = 0

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
