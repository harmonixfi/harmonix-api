import logging
from datetime import datetime, timedelta, timezone
from operator import and_

from core import constants
from log import setup_logging_to_console, setup_logging_to_file

from models.deposit_summary_snapshot import DepositSummarySnapshot
from models.funding_history import FundingHistory
from models.onchain_transaction_history import OnchainTransactionHistory
from models.vaults import Vault
from services import aevo_service, gold_link_service, hyperliquid_service
from services import bsx_service
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

from utils.vault_utils import (
    convert_to_nanoseconds,
    datetime_to_unix_ms,
    get_deposit_method_ids,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


session = Session(engine)


PARTNER = {
    "BSX": "BSX",
    "AEVO": "AEVO",
    "HYPERLIQUID": "HYPERLIQUID",
    "GOLDLINK": "GOLDLINK",
}


def fetch_funding_history(
    service_func, use_nanoseconds: bool = True, should_init: bool = False
):
    logger.info("Starting funding history calculation...")
    # Start date is set to 2024-04-05 which corresponds to the launch date
    # Ignoring vault "Koi & Chill with Kelp DAO" (ethereum-kelpdao-restaking-delta-neutral-vault)
    # as it requires special handling
    # start_time = datetime(2024, 4, 5, 0, 0, 0)
    start_time = datetime(2024, 4, 5, 0, 0, 0, tzinfo=timezone.utc)
    end_time = datetime.now(tz=timezone.utc)
    time_interval = timedelta(days=1)

    date_ranges = []
    current_time = start_time

    logger.info(f"Fetching funding history from {start_time} to {end_time}...")

    while current_time < end_time:
        start_date = current_time
        end_date = start_date.replace(hour=23, minute=59, second=59)

        funding_histories = service_func(
            start_time=(
                convert_to_nanoseconds(start_date)
                if use_nanoseconds
                else datetime_to_unix_ms(start_date)
            ),
            end_time=(
                convert_to_nanoseconds(end_date)
                if use_nanoseconds
                else datetime_to_unix_ms(end_date)
            ),
        )
        date_ranges.extend(funding_histories)
        current_time += time_interval

    return date_ranges


def fetch_funding_history_bsx():
    try:
        logger.info("Starting BSX funding history fetch...")

        logger.info("Requesting funding history from BSX service...")
        funding_history = fetch_funding_history(
            service_func=bsx_service.get_funding_history
        )
        logger.info(f"Successfully fetched {len(funding_history)} records from BSX")

        logger.info("Processing BSX funding history data for database insertion...")
        funding_history_entries = [
            FundingHistory(
                datetime=item.datetime,
                funding_rate=item.funding_rate,
                partner_name=PARTNER["BSX"],
            )
            for item in funding_history
        ]

        entry_count = len(funding_history_entries)
        logger.info(f"Created {entry_count} BSX funding history entries for insertion")

        logger.info("Beginning BSX database transaction...")
        session.add_all(funding_history_entries)
        session.commit()
        logger.info(f"Successfully committed {entry_count} BSX records to database")

    except Exception as e:
        logger.error(f"Failed to process BSX funding history: {str(e)}", exc_info=True)
        session.rollback()
        raise


def fetch_funding_history_aevo():
    try:
        logger.info("Starting AEVO funding history fetch...")

        logger.info("Requesting funding history from AEVO service...")
        funding_history = fetch_funding_history(
            service_func=aevo_service.get_funding_history
        )
        logger.info(f"Successfully fetched {len(funding_history)} records from AEVO")

        logger.info("Processing AEVO funding history data for database insertion...")
        funding_history_entries = [
            FundingHistory(
                datetime=item.datetime,
                funding_rate=item.funding_rate,
                partner_name=PARTNER["AEVO"],
            )
            for item in funding_history
        ]

        entry_count = len(funding_history_entries)
        logger.info(f"Created {entry_count} AEVO funding history entries for insertion")

        logger.info("Beginning AEVO database transaction...")
        session.add_all(funding_history_entries)
        session.commit()
        logger.info(f"Successfully committed {entry_count} AEVO records to database")

    except Exception as e:
        logger.error(f"Failed to process AEVO funding history: {str(e)}", exc_info=True)
        session.rollback()
        raise


def fetch_funding_history_hyperliquid():
    try:
        logger.info("Starting Hyperliquid funding history fetch...")

        logger.info("Requesting funding history from Hyperliquid service...")
        funding_history = fetch_funding_history(
            service_func=hyperliquid_service.get_funding_history,
            use_nanoseconds=False,
        )
        logger.info(
            f"Successfully fetched {len(funding_history)} records from Hyperliquid"
        )

        logger.info(
            "Processing Hyperliquid funding history data for database insertion..."
        )
        funding_history_entries = [
            FundingHistory(
                datetime=item.datetime,
                funding_rate=item.funding_rate,
                partner_name=PARTNER["HYPERLIQUID"],
            )
            for item in funding_history
        ]

        entry_count = len(funding_history_entries)
        logger.info(
            f"Created {entry_count} Hyperliquid funding history entries for insertion"
        )

        logger.info("Beginning Hyperliquid database transaction...")
        session.add_all(funding_history_entries)
        session.commit()
        logger.info(
            f"Successfully committed {entry_count} Hyperliquid records to database"
        )

    except Exception as e:
        logger.error(
            f"Failed to process Hyperliquid funding history: {str(e)}", exc_info=True
        )
        session.rollback()
        raise


def fetch_funding_history_goldlink():
    try:
        logger.info("Starting Goldlink funding history fetch...")

        logger.info("Requesting funding history from Goldlink service...")
        funding_history = gold_link_service.get_funding_history()
        logger.info(
            f"Successfully fetched {len(funding_history)} records from Goldlink"
        )

        logger.info(
            "Processing Goldlink funding history data for database insertion..."
        )
        funding_history_entries = [
            FundingHistory(
                datetime=item.datetime.replace(tzinfo=timezone.utc),
                funding_rate=item.funding_rate,
                partner_name=PARTNER["GOLDLINK"],
            )
            for item in funding_history
        ]

        entry_count = len(funding_history_entries)
        logger.info(
            f"Created {entry_count} Goldlink funding history entries for insertion"
        )

        logger.info("Beginning Goldlink database transaction...")
        session.add_all(funding_history_entries)
        session.commit()
        logger.info(
            f"Successfully committed {entry_count} Goldlink records to database"
        )

    except Exception as e:
        logger.error(
            f"Failed to process Goldlink funding history: {str(e)}", exc_info=True
        )
        session.rollback()
        raise


if __name__ == "__main__":
    try:
        logger.info("Initializing funding history fetch process...")
        setup_logging_to_console()
        setup_logging_to_file("fetch_funding_history")

        for service_name, fetch_func in [
            ("BSX", fetch_funding_history_bsx),
            ("AEVO", fetch_funding_history_aevo),
            ("Hyperliquid", fetch_funding_history_hyperliquid),
            ("Goldlink", fetch_funding_history_goldlink),
        ]:
            try:
                logger.info(f"Starting {service_name} funding history fetch process...")
                fetch_func()
                logger.info(
                    f"Completed {service_name} funding history fetch successfully"
                )
            except Exception as e:
                logger.error(
                    f"Failed to fetch {service_name} funding history: {str(e)}",
                    exc_info=True,
                )
                # Continue with next service even if current one fails
                continue

        logger.info("All funding history fetch processes completed")

    except Exception as e:
        logger.error(
            f"Critical error in funding history fetch process: {str(e)}", exc_info=True
        )
        raise
    finally:
        logger.info("Funding history fetch process finished")
