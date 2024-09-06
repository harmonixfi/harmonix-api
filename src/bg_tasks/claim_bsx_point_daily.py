import logging
from datetime import datetime
from sqlmodel import Session

from log import setup_logging_to_console, setup_logging_to_file
from core.db import engine
from core import constants
from sqlmodel import Session, select

from services.vault_performance_history_service import VaultPerformanceHistoryService
from utils.web3_utils import parse_hex_to_int
from services.bsx_service import get_list_claim_bsx_point

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

session = Session(engine)


def claim_bsx_point_daily():
    try:
        bsx_points = get_list_claim_bsx_point()
        logger.info(f"Retrieved {len(bsx_points)} BSX points")
        # Process the bsx_points as needed
        # ...
    except Exception as e:
        logger.error(f"Error occurred while claiming BSX points: {str(e)}")


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file("claim_bsx_point_daily", logger=logger)
    claim_bsx_point_daily()
