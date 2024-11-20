import logging
from datetime import datetime, timedelta
from typing import List
import pandas as pd

from log import setup_logging_to_console, setup_logging_to_file
from core import constants

from services import bsx_service, gold_link_service, hyperliquid_service
from services import aevo_service
from utils.vault_utils import convert_to_nanoseconds, datetime_to_unix_ms


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add these constants for CSV file paths
CSV_PATH = {
    "BSX": "./data/funding_history_bsx.csv",
    "AEVO": "./data/funding_history_aevo.csv",
    "HYPERLIQUID": "./data/funding_history_hyperliquid.csv",
    "GOLDLINK": "./data/funding_history_goldlink.csv",
}


def fetch_funding_history(service_func, output_file, use_nanoseconds: bool = True):
    logger.info("Starting funding history calculation...")
    # Start date is set to 2024-04-05 which corresponds to the launch date
    # Ignoring vault "Koi & Chill with Kelp DAO" (ethereum-kelpdao-restaking-delta-neutral-vault)
    # as it requires special handling
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
        date_ranges.extend(funding_histories)
        current_time += time_interval

    data = [entry.dict() for entry in date_ranges]
    df = pd.DataFrame(data)
    df.to_csv(output_file, index=False)

    logger.info(f"Funding history saved to {output_file}")


def fetch_funding_history_bsx():
    logger.info("Fetching BSX funding history...")
    fetch_funding_history(
        service_func=bsx_service.get_funding_history,
        output_file=CSV_PATH["BSX"],
    )


def fetch_funding_history_aevo():
    logger.info("Fetching AEVO funding history...")
    fetch_funding_history(
        service_func=aevo_service.get_funding_history,
        output_file=CSV_PATH["AEVO"],
    )


def fetch_funding_history_hyperliquid():
    logger.info("Fetching Hyperliquid funding history...")
    fetch_funding_history(
        service_func=hyperliquid_service.get_funding_history,
        output_file=CSV_PATH["HYPERLIQUID"],
        use_nanoseconds=False,
    )


def fetch_funding_history_goldlink():
    logger.info("Fetching Goldlink funding history...")
    funding_histories = gold_link_service.get_funding_history()
    date_ranges = [
        {"datetime": entity.datetime, "funding_rate": entity.funding_rate}
        for entity in funding_histories
    ]
    df = pd.DataFrame(date_ranges)
    df.to_csv(CSV_PATH["GOLDLINK"], index=False)  # Use the constant

    logger.info(f"Funding history saved to goldlink")


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file(f"fetch_funding_history", logger=logger)
    fetch_funding_history_bsx()
    fetch_funding_history_aevo()
    fetch_funding_history_hyperliquid()
    fetch_funding_history_goldlink()
