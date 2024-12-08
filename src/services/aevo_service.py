from datetime import timezone
from typing import List
import requests
from core.config import settings
from schemas import FundingHistoryEntry
from utils.vault_utils import nanoseconds_to_datetime

url = settings.AEVO_API_URL


def get_funding_history(
    instrument_name: str = "ETH-PERP",
    start_time: int = 0,
    end_time: int = None,
    limit: int = 24,
) -> List[FundingHistoryEntry]:
    params = {
        "instrument_name": instrument_name,
        "start_time": start_time,
        "end_time": end_time,
        "limit": limit,
    }
    headers = {"accept": "application/json"}

    try:
        response = requests.get(
            f"{url}/funding-history", headers=headers, params=params
        )
        response.raise_for_status()  # Raise HTTPError for bad responses
        data = response.json()

        funding_history = data.get("funding_history", [])
        if funding_history:
            # Map the raw funding history to FundingHistoryEntry instances
            return [
                FundingHistoryEntry(
                    datetime=nanoseconds_to_datetime(int(entry[1])).astimezone(
                        timezone.utc
                    ),
                    funding_rate=float(entry[2]),
                )
                for entry in funding_history
            ]
        return []  # Return an empty list if no data is found

    except requests.RequestException as e:
        print(f"Error fetching funding history: {e}")
        return []
