import logging
from datetime import datetime, timedelta, timezone
from typing import List
import pandas as pd

from log import setup_logging_to_console, setup_logging_to_file
from core.db import engine
from core import constants

from schemas.funding_history_entry import FundingHistoryEntry
from services import bsx_service, gold_link_service, hyperliquid_service
from services import aevo_service
from utils.vault_utils import convert_to_nanoseconds, datetime_to_unix_ms


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add these constants for CSV file paths
FUNDING_HISTORY_BSX_CSV = "./data/funding_history_bsx.csv"
FUNDING_HISTORY_AEVO_CSV = "./data/funding_history_aevo.csv"
FUNDING_HISTORY_HYPERLIQUID_CSV = "./data/funding_history_hyperliquid.csv"
FUNDING_HISTORY_GOLDLINK_CSV = "./data/funding_history_goldlink.csv"


def calculate_average_funding_rate(funding_histories: List[FundingHistoryEntry]):
    funding_rates = [entry.funding_rate for entry in funding_histories]
    average_rate = sum(funding_rates) / len(funding_rates) if funding_rates else 0
    return average_rate


def fetch_funding_history(service_func, output_file, use_nanoseconds: bool = True):
    logger.info("Starting funding history calculation...")
    # init all vault : 2024-04-05
    start_time = datetime(2024, 4, 5, 0, 0, 0)
    end_time = datetime.now()
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

        funding_history_avg = calculate_average_funding_rate(funding_histories)

        date_ranges.append(
            {"datetime": start_date, "funding_history": funding_history_avg}
        )
        current_time += time_interval

    df = pd.DataFrame(date_ranges)
    df.to_csv(output_file, index=False)

    logger.info(f"Funding history saved to {output_file}")


def fetch_funding_history_bsx():
    logger.info("Fetching BSX funding history...")
    fetch_funding_history(
        service_func=bsx_service.get_funding_history,
        output_file=FUNDING_HISTORY_BSX_CSV,  # Use the constant
    )


def fetch_funding_history_aevo():
    logger.info("Fetching AEVO funding history...")
    fetch_funding_history(
        service_func=aevo_service.get_funding_history,
        output_file=FUNDING_HISTORY_AEVO_CSV,
    )


def fetch_funding_history_hyperliquid():
    logger.info("Fetching Hyperliquid funding history...")
    fetch_funding_history(
        service_func=hyperliquid_service.get_funding_history,
        output_file=FUNDING_HISTORY_HYPERLIQUID_CSV,
        use_nanoseconds=False,
    )


def fetch_funding_history_goldlink():
    logger.info("Fetching Goldlink funding history...")
    funding_histories = gold_link_service.get_funding_history()
    date_ranges = [
        {"datetime": entity.datetime, "funding_history": entity.funding_rate}
        for entity in funding_histories
    ]
    df = pd.DataFrame(date_ranges)
    df.to_csv(FUNDING_HISTORY_GOLDLINK_CSV, index=False)  # Use the constant

    logger.info(f"Funding history saved to goldlink")


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file(f"fetch_funding_history", logger=logger)
    fetch_funding_history_bsx()
    fetch_funding_history_aevo()
    fetch_funding_history_hyperliquid()
    fetch_funding_history_goldlink()
