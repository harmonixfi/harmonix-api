import logging
from datetime import datetime, timedelta, timezone
from typing import List
import uuid
from sqlalchemy import and_, func
from sqlmodel import Session, select

from log import setup_logging_to_console, setup_logging_to_file
from models.onchain_transaction_history import OnchainTransactionHistory
from models.vault_performance import VaultPerformance
from models.vault_performance_history import VaultPerformanceHistory
from models.vaults import Vault
from core.db import engine
from core import constants
from sqlmodel import Session, select


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

session = Session(engine)


def get_active_vaults():
    return session.exec(select(Vault).where(Vault.is_active)).all()


def get_vault_performances(vault_id: uuid.UUID, date: datetime):
    date_query = date.date()
    data = session.exec(
        select(VaultPerformance)
        .where(VaultPerformance.vault_id == vault_id)
        .where(func.date(VaultPerformance.datetime) == date_query)
        .order_by(VaultPerformance.datetime.asc())
    ).all()
    return data


def process_vault_performance(vault, datetime: datetime) -> float:
    """Process performance for a given vault."""

    current_tvl = 0
    previous_vault_performances_tvl = 0
    if vault.network_chain == constants.CHAIN_ETHER_MAINNET:
        # Friday of weelky
        if datetime.weekday() == 4:
            friday_this_week = datetime
            friday_last_week = friday_this_week - timedelta(days=7)
            previous_vault_performances = get_vault_performances(vault.id, friday_last_week)
            previous_vault_performances_tvl = sum(
            float(v.total_locked_value) for v in previous_vault_performances
            )
        else:
            days_since_friday = (datetime.weekday() - 4) % 7
            friday_this_week = datetime - timedelta(days=days_since_friday)
            previous_vault_performances_tvl = 0

        vault_performances = get_vault_performances(vault.id, friday_this_week)
        current_tvl = sum(float(v.total_locked_value) for v in vault_performances)

        

    else:
        vault_performances = get_vault_performances(vault.id, datetime)
        current_tvl = sum(float(v.total_locked_value) for v in vault_performances)

        previous_vault_performances = get_vault_performances(
            vault.id, datetime - timedelta(days=1)
        )

        previous_vault_performances_tvl = sum(
            float(v.total_locked_value) for v in previous_vault_performances
        )

    tvl_change = current_tvl - previous_vault_performances_tvl

    tvl_change = current_tvl - previous_vault_performances_tvl

    total_deposit = calculate_total_deposit(datetime.date())
    return tvl_change - total_deposit


def calculate_total_deposit(vault_performance_date):
    """Calculate the total deposits for a specific date."""
    deposits_query = select(OnchainTransactionHistory).where(
        OnchainTransactionHistory.method_id == constants.MethodID.DEPOSIT,
        func.date(func.to_timestamp(OnchainTransactionHistory.timestamp))
        == vault_performance_date,
    )
    deposits = session.exec(deposits_query).all()
    return sum(float(tx.value) for tx in deposits)


def insert_vault_performance_history(
    yield_data: float, vault_id: uuid.UUID, datetime: datetime
):
    vault_performance_history = VaultPerformanceHistory(
        datetime=datetime, total_locked_value=yield_data, vault_id=vault_id
    )
    session.add(vault_performance_history)
    session.commit()


def get_vault_performance_dates() -> List[datetime]:
    start_date = datetime(2024, 6, 7)
    end_date = datetime.now() - timedelta(days=1)

    date_list = []
    current_date = start_date

    while current_date <= end_date:
        date_list.append(current_date)
        current_date += timedelta(days=1)

    return date_list


def calculate_yield_init():
    logger.info("Starting calculate Yield init...")

    vaults = get_active_vaults()
    vault_performance_dates = get_vault_performance_dates()

    for vault in vaults:
        # print('-----------------------valut------------------')
        if vault.network_chain == constants.CHAIN_ETHER_MAINNET:
            for vault_performance_date in vault_performance_dates:
                yield_data = process_vault_performance(vault, vault_performance_date)
                insert_vault_performance_history(
                    yield_data=yield_data,
                    vault_id=vault.id,
                    datetime=vault_performance_date,
                )
        else:
            # for vault_performance_date in vault_performance_dates:
            #     yield_data = process_vault_performance(vault, vault_performance_date)
            #     # if yield_data < 0:
            #     #     print('sai meo r----------------------------')
            #     insert_vault_performance_history(
            #         yield_data=yield_data,
            #         vault_id=vault.id,
            #         datetime=vault_performance_date,
            #     )
            continue
            # print('***********************end----valut------------------')


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file(f"calculate_yield_day_init", logger=logger)
    calculate_yield_init()
