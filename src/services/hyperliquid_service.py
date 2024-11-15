from datetime import datetime, timedelta, timezone
import json
import math
import requests
from core.config import settings

url = settings.HYPERLIQUID_URL

ALLOCATION_RATIO: float = 1 / 2


def calculate_projected_apy(component_apy: float):
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
    avg_8h_funding_rate = sum(funding_rates) / len(funding_rates)
    # Calculate the projected APY based on the average funding rate
    projected_apy = (
        avg_8h_funding_rate * ALLOCATION_RATIO
        + (component_apy / 100) * ALLOCATION_RATIO
    )
    projected_apy_annualized = projected_apy * 24 * 365
    return projected_apy_annualized
