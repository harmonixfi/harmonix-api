import logging
from datetime import datetime, timedelta
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

from utils.web3_utils import parse_hex_to_int


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


def get_tvl(vault_id: uuid.UUID, datetime: datetime) -> float:
    vault_performances = get_vault_performances(vault_id, datetime)
    return sum(float(v.total_locked_value) for v in vault_performances)


def process_vault_performance(vault, datetime: datetime) -> float:
    """Process performance for a given vault."""

    current_tvl = 0
    previous_vault_performances_tvl = 0
    if vault.network_chain == constants.CHAIN_ETHER_MAINNET:
        # Friday of weelky
        if datetime.weekday() == 4:
            friday_this_week = datetime
            friday_last_week = friday_this_week - timedelta(days=7)
            current_tvl = get_tvl(vault.id, friday_this_week)
            previous_vault_performances_tvl = get_tvl(vault.id, friday_last_week)

    else:
        current_tvl = get_tvl(vault.id, datetime)
        previous_vault_performances_tvl = get_tvl(
            vault.id, datetime - timedelta(days=1)
        )

    tvl_change = current_tvl - previous_vault_performances_tvl

    total_deposit = calculate_total_deposit(datetime, vault=vault)
    return tvl_change - total_deposit


def to_tx_aumount(input_data: str):
    input_data = input_data[10:].lower()
    amount = input_data[:64]
    return float(parse_hex_to_int(amount) / 1e6)


def calculate_total_deposit(datetime: datetime, vault: Vault):
    """Calculate the total deposits for a specific date."""
    end_date = int(datetime.timestamp())
    start_date = int((datetime - timedelta(hours=24)).timestamp())

    deposits_query = (
        select(OnchainTransactionHistory)
        .where(OnchainTransactionHistory.method_id == constants.MethodID.DEPOSIT.value)
        .where(OnchainTransactionHistory.to_address == vault.contract_address.lower())
        .where(OnchainTransactionHistory.timestamp <= end_date)
        .where(OnchainTransactionHistory.timestamp >= start_date)
    )

    deposits = session.exec(deposits_query).all()

    withdraw_query = (
        select(OnchainTransactionHistory)
        .where(
            OnchainTransactionHistory.method_id
            == constants.MethodID.COMPPLETE_WITHDRAWAL.value,
        )
        .where(OnchainTransactionHistory.to_address == vault.contract_address.lower())
        .where(OnchainTransactionHistory.timestamp <= end_date)
        .where(OnchainTransactionHistory.timestamp >= start_date)
    )

    withdraw = session.exec(withdraw_query).all()

    return sum(to_tx_aumount(tx.input) for tx in deposits) - sum(
        to_tx_aumount(tx.input) for tx in withdraw
    )


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
        if vault.network_chain == constants.CHAIN_ETHER_MAINNET:
            if now.weekday() == 4:
                yield_data = process_vault_performance(vault, now)
                insert_vault_performance_history(
                    yield_data=yield_data,
                    vault_id=vault.id,
                    datetime=now,
                )
            else:
                continue
        else:
            yield_data = process_vault_performance(vault, now)
            insert_vault_performance_history(
                yield_data=yield_data,
                vault_id=vault.id,
                datetime=now,
            )


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file(f"calculate_yield_day", logger=logger)
    calculate_yield_day()
