import logging
from datetime import datetime
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


def calculate_tvl_change(vault_id, last_24h_timestamp) -> float:
    """Calculate the change in TVL for a given vault over the last 24 hours."""
    previous_tvl = get_previous_tvl(vault_id, last_24h_timestamp)
    current_tvl = get_current_tvl(vault_id)
    return (current_tvl or 0) - (previous_tvl or 0)


def get_previous_tvl(vault_id, last_24h_timestamp) -> float:
    """Get the total locked value (TVL) for a vault 24 hours ago."""
    subquery = (
        select(VaultPerformance.datetime)
        .where(VaultPerformance.datetime <= datetime.fromtimestamp(last_24h_timestamp))
        .where(VaultPerformance.vault_id == vault_id)
        .order_by(VaultPerformance.datetime.desc())
        .limit(1)
    ).subquery()

    previous_tvl_query = (
        select(func.sum(VaultPerformance.total_locked_value))
        .where(VaultPerformance.datetime == subquery.c.datetime)
        .where(VaultPerformance.vault_id == vault_id)
    )
    return session.exec(previous_tvl_query).first()


def get_current_tvl(vault_id) -> float:
    """Get the current total locked value (TVL) for a vault."""
    subquery = (
        select(VaultPerformance.datetime)
        .where(VaultPerformance.vault_id == vault_id)
        .order_by(VaultPerformance.datetime.desc())
        .limit(1)
    ).subquery()

    current_tvl_query = (
        select(func.sum(VaultPerformance.total_locked_value))
        .where(VaultPerformance.datetime == subquery.c.datetime)
        .where(VaultPerformance.vault_id == vault_id)
    )
    return session.exec(current_tvl_query).first()


def process_vault_performance(vault, datetime: datetime) -> float:
    """Process performance for a given vault."""

    now_timestamp = int(datetime.timestamp())
    last_24h_timestamp = now_timestamp - 24 * 3600

    total_deposit = calculate_total_deposit(last_24h_timestamp)
    tvl_change = calculate_tvl_change(vault.id, last_24h_timestamp)

    return tvl_change - total_deposit


def calculate_total_deposit(last_24h_timestamp: int):
    """Calculate the total deposits for a specific date."""
    deposit_query = (
        select(OnchainTransactionHistory)
        .where(OnchainTransactionHistory.method_id == constants.MethodID.DEPOSIT)
        .where(OnchainTransactionHistory.timestamp >= last_24h_timestamp)
    )
    deposits = session.exec(deposit_query).all()
    return sum(float(tx.value) for tx in deposits)


def insert_vault_performance_history(
    yield_data: float, vault_id: uuid.UUID, datetime: datetime
):
    vault_performance_history = VaultPerformanceHistory(
        datetime=datetime, total_locked_value=yield_data, vault_id=vault_id
    )
    session.add(vault_performance_history)
    session.commit()


def calculate_yield_day():
    logger.info("Starting calculate day...")

    vaults = get_active_vaults()

    now = datetime.now()
    for vault in vaults:
        # print('-----------------------valut------------------')
        yield_data = process_vault_performance(vault, now)
        insert_vault_performance_history(
            yield_data=yield_data,
            vault_id=vault.id,
            datetime=now,
        )
        # print('***********************end----valut------------------')


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file(f"calculate_yield_day", logger=logger)
    calculate_yield_day()
