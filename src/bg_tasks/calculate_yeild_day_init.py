import logging
from datetime import datetime, timedelta, timezone
import uuid
from sqlalchemy import func
from sqlmodel import Session, select

from bg_tasks.indexing_user_holding_kelpdao import get_pps
from log import setup_logging_to_console, setup_logging_to_file
from models.onchain_transaction_history import OnchainTransactionHistory
from models.vault_performance import VaultPerformance
from models.vault_performance_history import VaultPerformanceHistory
from models.vaults import Vault
from core.db import engine
from core import constants
from sqlmodel import Session, select

from utils.web3_utils import get_vault_contract, parse_hex_to_int

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

session = Session(engine)


def get_active_vaults():
    return session.exec(select(Vault).where(Vault.is_active)).all()


def get_vault_performance_dates():
    """Retrieve all vault performance dates based on the subquery."""
    subquery = (
        select(
            VaultPerformance.vault_id,
            func.date_trunc("day", VaultPerformance.datetime).label("day"),
            func.min(VaultPerformance.datetime).label("min_datetime"),
        )
        .group_by(VaultPerformance.vault_id, "day")
        .subquery()
    )

    vault_performance_query = (
        select(VaultPerformance.datetime)
        .join(
            subquery,
            VaultPerformance.datetime == subquery.c.min_datetime,
        )
        .order_by(VaultPerformance.datetime.asc())
    )

    return session.exec(vault_performance_query).all()


def get_vault_performances(vault_id, datetime: datetime):
    return session.exec(
        select(VaultPerformance)
        .where(VaultPerformance.vault_id == vault_id)
        .where(VaultPerformance.datetime.date() == datetime.date())
        .order_by(VaultPerformance.datetime.asc())
    ).all()


def process_vault_performance(vault, datetime: datetime):
    """Process performance for a given vault."""
    vault_performances = get_vault_performances(vault.id, datetime)
    current_tvl = sum(float(v.total_locked_value) for v in vault_performances)

    previous_vault_performances = get_vault_performances(
        vault.id, datetime - timedelta(days=1)
    )
    previous_vault_performances_tvl = sum(
        float(v.total_locked_value) for v in previous_vault_performances
    )

    total_deposit = calculate_total_deposit(datetime.date())


def calculate_total_deposit(vault_performance_date):
    """Calculate the total deposits for a specific date."""
    deposits_query = select(OnchainTransactionHistory).where(
        OnchainTransactionHistory.method_id == constants.MethodID.DEPOSIT,
        func.date(func.to_timestamp(OnchainTransactionHistory.timestamp))
        == vault_performance_date,
    )
    deposits = session.exec(deposits_query).all()
    return sum(float(tx.value) for tx in deposits)


def calculate_yield_init():
    logger.info("Starting calculate Yield init...")

    vaults = get_active_vaults()
    vault_performance_dates = get_vault_performance_dates()

    for vault in vaults:
        for vault_performance_date in vault_performance_dates:
            process_vault_performance(vault, vault_performance_date)


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file(f"calculate_yeild_day_init", logger=logger)
    calculate_yield_init()
