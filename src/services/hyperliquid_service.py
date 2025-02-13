from datetime import datetime, timedelta, timezone
import json
import math
import time
from typing import List
import requests
from core.config import settings
from schemas.funding_history_entry import FundingHistoryEntry
from utils.vault_utils import unixtimestamp_to_datetime

url = settings.HYPERLIQUID_URL
TOKEN_DELEGATE_TYPE = "tokenDelegate"


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

        time.sleep(0.6)
        if isinstance(data, list):
            return [
                FundingHistoryEntry(
                    datetime=unixtimestamp_to_datetime(int(entry["time"])).astimezone(
                        timezone.utc
                    ),
                    funding_rate=float(entry["fundingRate"]),
                )
                for entry in data
            ]

        return []

    except requests.RequestException as e:
        print(f"Error Hyperliquid fetching funding history: {e}")
        return []


def get_funding_history_hype(
    start_time: int = 0,
    end_time: int = None,
    limit: int = 24,
) -> List[FundingHistoryEntry]:
    return get_funding_history(
        "HYPE", start_time=start_time, end_time=end_time, limit=limit
    )


def is_valid_token_delegate_transaction(tx_hash: str, user_address: str) -> bool:
    try:
        payload = json.dumps({"hash": tx_hash, "type": "txDetails"})
        headers = {"Content-Type": "application/json"}

        response = requests.post(
            settings.HYPERLIQUID_EXPLORER_URL, headers=headers, data=payload
        )

        response.raise_for_status()

        data = response.json()

        tx_user = data.get("tx", {}).get("user")
        action_type = data.get("tx", {}).get("action", {}).get("type")

        return (
            tx_user
            and tx_user.lower() == user_address.lower()
            and action_type == "tokenDelegate"
        )

    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
    except json.JSONDecodeError:
        print("Error decoding JSON response")
    except Exception as e:
        print(f"Unexpected error: {e}")

    return False


def get_info_stake(user_address: str):
    payload = {"type": "delegations", "user": user_address}
    headers = {"accept": "application/json"}

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, list):
            return [
                {
                    "validator": item.get("validator", ""),
                    "amount": item.get("amount", ""),
                }
                for item in data
            ]

        return []

    except requests.RequestException as e:
        print(f"Error fetching validator data: {e}")
        return []
