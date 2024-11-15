from datetime import datetime, timedelta, timezone
import json
import math
import requests
from core.config import settings

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
