from datetime import datetime, timedelta, timezone
import logging
from log import setup_logging_to_console, setup_logging_to_file
from models.goldlink_borrow_rate_history import GoldlinkBorrowRateHistory
from reports.ultils import PARTNER
from services import gold_link_service

from sqlalchemy import func
from sqlmodel import Session, select

from core.db import engine

logger = logging.getLogger(__name__)
session = Session(engine)


def fetch_goldlink_borrow_rate_history():
    try:
        logger.info("Starting Goldlink borrow rate history fetch process...")
        apy_rate = gold_link_service.get_apy_rate_history()

        if not apy_rate:
            logger.error(
                "No borrow rate history found for Goldlink. Skipping database update."
            )
            return

        try:
            apy_rate_history_entries = [
                GoldlinkBorrowRateHistory(datetime=timestamp, apy_rate=apy_rate)
                for record in apy_rate
                for timestamp, apy_rate in record.items()
            ]
            session.add_all(apy_rate_history_entries)
            session.commit()

            logger.info(f"Successfully borrow rate records to database")

        except Exception as db_error:
            logger.error(
                f"Database operation failed while saving borrow rate history: {str(db_error)}",
                exc_info=True,
            )
            session.rollback()
            raise

    except Exception as e:
        logger.error(
            f"Failed to fetch or process Goldlink borrow rate history: {str(e)}",
            exc_info=True,
        )
        session.rollback()
        raise


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file("fetch_goldlink_borrow_rate_history")
    fetch_goldlink_borrow_rate_history()
