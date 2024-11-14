from datetime import datetime, timedelta, timezone
import json
import requests
from core.config import settings

url = settings.HYPERLIQUID_URL

ALLOCATION_RATIO: float = 1 / 2


def calculate_projected_apy():
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

    # Calculate the average funding rate over the 8-hour period
    average_funding_rate = sum(funding_rates) / len(funding_rates)

    # Calculate the projected APY based on the average funding rate
    projected_apy = average_funding_rate * ALLOCATION_RATIO + 0.04 * ALLOCATION_RATIO

    return projected_apy
