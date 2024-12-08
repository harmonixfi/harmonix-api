import logging
from datetime import datetime, timedelta, timezone
from operator import and_

from core import constants
from log import setup_logging_to_console, setup_logging_to_file

from models.deposit_summary_snapshot import DepositSummarySnapshot
from models.onchain_transaction_history import OnchainTransactionHistory
from models.vaults import Vault
from services.bsx_service import claim_point, get_list_claim_point
from services.market_data import get_klines
from services.vault_contract_service import VaultContractService

from sqlalchemy import func
from sqlmodel import Session, select
from datetime import datetime, timedelta

from core import constants
from models.onchain_transaction_history import OnchainTransactionHistory
from models.vaults import Vault
from services.vault_contract_service import VaultContractService
from utils.extension_utils import (
    to_amount_pendle,
    to_tx_aumount,
    to_tx_aumount_goldlink,
    to_tx_aumount_rethink,
)
from core.db import engine

from utils.vault_utils import get_deposit_method_ids

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


session = Session(engine)


def get_vault_by_address(to_address: str):
    """Retrieve the Vault instance based on the given address."""
    vault_addresses = VaultContractService().get_vault_address_by_contract(
        to_address.lower()
    )
    return session.exec(
        select(Vault).where(
            func.lower(Vault.contract_address).in_(
                [addr.lower() for addr in vault_addresses]
            )
        )
    ).first()


def calculate_rethink_amount_value(deposit: OnchainTransactionHistory):
    """Calculate the amount value for rethink strategy."""
    converted_datetime = datetime.fromtimestamp(deposit.timestamp)
    w_eth_price = float(
        get_klines(
            "ETHUSDT",
            start_time=converted_datetime,
            end_time=converted_datetime.utcnow() + timedelta(minutes=15),
            interval="15m",
            limit=1,
        )[0][4]
    )
    if deposit.method_id == constants.MethodID.DEPOSIT_RETHINK1.value:
        amount = float(deposit.value)
    else:
        amount = to_tx_aumount_rethink(deposit.input)
    return amount * w_eth_price


def calculate_total_deposit(deposits: list[OnchainTransactionHistory]):
    """Calculate the total deposit amount based on strategy and vault."""
    total_deposit = 0
    for deposit in deposits:
        vault = get_vault_by_address(deposit.to_address)
        if not vault:
            continue

        if vault.strategy_name == constants.PENDLE_HEDGING_STRATEGY:
            total_deposit += to_amount_pendle(
                deposit.input, int(deposit.block_number), vault.network_chain
            )
        elif vault.slug == constants.GOLD_LINK_SLUG:
            total_deposit += to_tx_aumount_goldlink(deposit.input)
        elif vault.slug == constants.ETH_WITH_LENDING_BOOST_YIELD:
            total_deposit += calculate_rethink_amount_value(deposit)
        else:
            total_deposit += to_tx_aumount(deposit.input)

    return total_deposit


def fetch_deposits_in_last_days(days: int):
    """Fetch deposits within the specified number of days."""
    method_ids = get_deposit_method_ids()
    start_date = datetime.now(tz=timezone.utc) - timedelta(days=days)
    start_timestamp = int(start_date.timestamp())

    query = select(OnchainTransactionHistory).where(
        and_(
            OnchainTransactionHistory.method_id.in_(method_ids),
            OnchainTransactionHistory.timestamp >= start_timestamp,
        )
    )
    return session.exec(query).all()


def calculate_report_deposit_summary(days: int):
    """Generate a report summary of total deposits within the specified number of days."""
    deposits = fetch_deposits_in_last_days(days)
    total_deposit = calculate_total_deposit(deposits)
    return total_deposit


def save_db(total_deposit_7_day: float, total_deposit_30_day: float):
    report = DepositSummarySnapshot(
        datetime=datetime.now(tz=timezone.utc),
        deposit_7_day=total_deposit_7_day,
        deposit_30_day=total_deposit_30_day,
    )

    session.add(report)
    session.commit()


if __name__ == "__main__":
    try:
        # Setup logging before any operations
        setup_logging_to_console()
        setup_logging_to_file("calculate_report_deposit_summary")

        logger.info("Starting deposit summary calculation...")

        logger.info("Calculating report for 30 days...")
        total_deposit_30_day = calculate_report_deposit_summary(30)

        logger.info("Calculating report for 7 days...")
        total_deposit_7_day = calculate_report_deposit_summary(7)

        save_db(total_deposit_7_day, total_deposit_30_day)
        logger.info("Deposit summary calculation completed")
    except Exception as e:
        logger.error(f"Error in deposit summary calculation: {str(e)}", exc_info=True)
        raise
