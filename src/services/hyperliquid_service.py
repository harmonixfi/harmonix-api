from datetime import datetime, timedelta, timezone
import json
import math
from typing import List
import requests
from core.config import settings
from schemas.funding_history_entry import FundingHistoryEntry
from utils.vault_utils import unixtimestamp_to_datetime

url = settings.HYPERLIQUID_URL


def get_avg_8h_funding_rate() -> float:
    eight_hours_ago = datetime.now(tz=timezone.utc) - timedelta(hours=8)
    start_timestamp = int(eight_hours_ago.timestamp() * 1000)

    payload = json.dumps(
        {"type": "fundingHistory", "coin": "ETH", "startTime": start_timestamp}
    )
    headers = {"Content-Type": "application/json"}

    response = requests.post(url, headers=headers, data=payload)

    if response.status_code != 200:
        raise Exception("Failed to retrieve funding data")

    data = response.json()
    funding_rates = [
        float(entry["fundingRate"]) for entry in data if "fundingRate" in entry
    ]

    if not funding_rates:
        return 0
    avg_8h_funding_rate = sum(funding_rates) / len(funding_rates)
    return avg_8h_funding_rate


def get_funding_history(
    coin: str = "ETH",
    start_time: int = 0,
    end_time: int = None,
    limit: int = 24,
) -> List[FundingHistoryEntry]:
    payload = {
        "type": "fundingHistory",
        "coin": coin,
        "startTime": start_time,
        "endTime": end_time,
    }
    headers = {"accept": "application/json"}

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, list):
            return [
                FundingHistoryEntry(
                    datetime=unixtimestamp_to_datetime(int(entry["time"])),
                    funding_rate=float(entry["fundingRate"]),
                )
                for entry in data
            ]

        return []

    except requests.RequestException as e:
        print(f"Error Hyperliquid fetching funding history: {e}")
        return []
