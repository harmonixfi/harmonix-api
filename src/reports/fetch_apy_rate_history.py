import logging
from log import setup_logging_to_console, setup_logging_to_file

from models.apy_rate_history import APYRateHistory
from reports.fetch_funding_history import PARTNER
from services import gold_link_service

from sqlalchemy import func
from sqlmodel import Session, select

from core.db import engine


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


session = Session(engine)


def fetch_apy_rate_history_goldlink():
    try:
        logger.info("Starting to fetch Goldlink APY rate funding history...")

        apy_rate = gold_link_service.get_apy_rate_history()
        if not apy_rate:
            logger.warning(
                "No APY rate history found for Goldlink. Skipping database update."
            )
            return

        try:
            apy_rate_history_entries = [
                APYRateHistory(
                    datetime=timestamp,
                    apy_rate=apy_rate,
                    partner_name=PARTNER["GOLDLINK"],
                )
                for record in apy_rate
                for timestamp, apy_rate in record.items()
            ]
            session.add_all(apy_rate_history_entries)
            session.commit()

            logger.info(
                f"Successfully saved {len(apy_rate_history_entries)} APY rate records to database"
            )

        except Exception as db_error:
            logger.error(
                f"Database operation failed while saving APY rate history: {str(db_error)}",
                exc_info=True,
            )
            session.rollback()
            raise

    except Exception as e:
        logger.error(
            f"Failed to fetch or process Goldlink APY rate history: {str(e)}",
            exc_info=True,
        )
        session.rollback()
        raise


if __name__ == "__main__":

    setup_logging_to_console()
    setup_logging_to_file("fetch_apy_rate_history")
    fetch_apy_rate_history_goldlink()
