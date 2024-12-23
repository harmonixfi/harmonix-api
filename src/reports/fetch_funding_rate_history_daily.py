import logging
from datetime import datetime, timedelta, timezone
from operator import and_

from log import setup_logging_to_console, setup_logging_to_file

from models.funding_rate_history import FundingRateHistory
from reports.ultils import PARTNER
from services import aevo_service, gold_link_service, hyperliquid_service
from services import bsx_service

from sqlalchemy import func
from sqlmodel import Session, select
from datetime import datetime, timedelta

from core.db import engine

from utils.vault_utils import convert_to_nanoseconds, datetime_to_unix_ms

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


session = Session(engine)


def get_latest_funding_rate_date(partner_name: str) -> datetime:
    return session.exec(
        select(FundingRateHistory.datetime)
        .where(FundingRateHistory.partner_name == partner_name)
        .order_by(FundingRateHistory.datetime.desc())
    ).first()


def fetch_funding_history(
    service_func, start_date: datetime, use_nanoseconds: bool = True
):
    logger.info("Starting funding history calculation...")

    end_date = datetime.now(tz=timezone.utc)

    date_ranges = []

    logger.info(f"Fetching funding history from {start_date} to {end_date}...")

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

    return date_ranges


def fetch_funding_history_bsx():
    try:
        logger.info("Starting BSX funding history fetch...")

        logger.info("Requesting funding history from BSX service...")
        funding_history = fetch_funding_history(
            service_func=bsx_service.get_funding_history,
            start_date=get_latest_funding_rate_date(PARTNER["BSX"]),
        )
        logger.info(f"Successfully fetched {len(funding_history)} records from BSX")

        logger.info("Processing BSX funding history data for database insertion...")
        funding_history_entries = [
            FundingRateHistory(
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
            service_func=aevo_service.get_funding_history,
            start_date=get_latest_funding_rate_date(PARTNER["AEVO"]),
        )
        logger.info(f"Successfully fetched {len(funding_history)} records from AEVO")

        logger.info("Processing AEVO funding history data for database insertion...")
        funding_history_entries = [
            FundingRateHistory(
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
            start_date=get_latest_funding_rate_date(PARTNER["HYPERLIQUID"]),
            use_nanoseconds=False,
        )
        logger.info(
            f"Successfully fetched {len(funding_history)} records from Hyperliquid"
        )

        logger.info(
            "Processing Hyperliquid funding history data for database insertion..."
        )
        funding_history_entries = [
            FundingRateHistory(
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
        latest_funding_rate_date = get_latest_funding_rate_date(PARTNER["GOLDLINK"])
        funding_history_entries = [
            FundingRateHistory(
                datetime=item.datetime.replace(tzinfo=timezone.utc),
                funding_rate=item.funding_rate,
                partner_name=PARTNER["GOLDLINK"],
            )
            for item in funding_history
            if item.datetime.replace(tzinfo=timezone.utc) > latest_funding_rate_date
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


def fetch_funding_history_hyperliquid_hype_token():
    try:
        logger.info("Starting Hyperliquid funding history fetch HYPE token...")

        logger.info("Requesting funding history from Hyperliquid service...")
        start_date = get_latest_funding_rate_date(PARTNER["HYPERLIQUID_HYPE"]) or (
            datetime.now(tz=timezone.utc) - timedelta(days=1)
        )

        funding_history = fetch_funding_history(
            service_func=hyperliquid_service.get_funding_history_hype,
            start_date=start_date,
            use_nanoseconds=False,
        )
        logger.info(
            f"Successfully fetched {len(funding_history)} records from Hyperliquid HYPE token"
        )

        logger.info(
            "Processing Hyperliquid HYPE token funding history data for database insertion..."
        )
        funding_history_entries = [
            FundingRateHistory(
                datetime=item.datetime,
                funding_rate=item.funding_rate,
                partner_name=PARTNER["HYPERLIQUID_HYPE"],
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


if __name__ == "__main__":
    try:
        logger.info("Initializing funding rate history fetch process...")
        setup_logging_to_console()
        setup_logging_to_file("fetch_funding_rate_history_daily")

        handler = [
            fetch_funding_history_bsx,
            fetch_funding_history_aevo,
            fetch_funding_history_hyperliquid,
            fetch_funding_history_goldlink,
            fetch_funding_history_hyperliquid_hype_token,
        ]

        for fetch_func in handler:
            fetch_func()

        logger.info("All funding rate history fetch processes completed")

    except Exception as e:
        logger.error(
            f"Critical error in rate funding history fetch process: {str(e)}",
            exc_info=True,
        )
        raise
    finally:
        logger.info("Funding rate history  fetch process finished")
