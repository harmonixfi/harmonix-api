from datetime import datetime, timezone
from typing import Any, List
import requests
from core.config import settings
from schemas.bsx_point import BSXPoint
from schemas.funding_history_entry import FundingHistoryEntry
from utils.vault_utils import nanoseconds_to_datetime

api_key = settings.BSX_API_KEY
secret = settings.BSX_SECRET
bsx_base_url = settings.BSX_BASE_API_URL


def create_header() -> dict[str, Any]:
    return {
        "accept": "application/json",
        "accept-language": "en-US,en;q=0.9,vi;q=0.8",
        "bsx-key": api_key,
        "bsx-secret": secret,
        "cache-control": "no-cache",
        "origin": bsx_base_url,
        "pragma": "no-cache",
        "priority": "u=1, i",
        "referer": bsx_base_url,
        "sec-ch-ua": '"Not)A;Brand";v="99", "Microsoft Edge";v="127", "Chromium";v="127"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0",
    }


def get_points_earned() -> float:
    headers = create_header()

    response = requests.get(f"{bsx_base_url}/points/trading", headers=headers)

    if response.status_code == 200:
        data = response.json()
        total = data.get("total_points_earned")
        return float(total) if total is not None else 0.0
    else:
        raise Exception(f"Request failed with status {response.status_code}")


def get_list_claim_point() -> List[BSXPoint]:
    try:
        api_url = f"{bsx_base_url}/points/trading"
        headers = create_header()
        response = requests.get(api_url, headers=headers)

        if response.status_code == 200:
            data = response.json()["epochs"]
            return [
                BSXPoint(
                    start_at=epoch["start_at"],
                    end_at=epoch["end_at"],
                    point=float(epoch["point"]),
                    degen_point=float(epoch["degen_point"]),
                    status=epoch["status"],
                    claim_deadline=datetime.fromtimestamp(
                        int(epoch["claim_deadline"]) / 1e9, tz=timezone.utc
                    ),
                    claimed_at=(
                        datetime.fromtimestamp(
                            int(epoch["claimed_at"]) / 1e9, tz=timezone.utc
                        )
                        if epoch["claimed_at"] != "0"
                        else None
                    ),
                    claimable=epoch["claimable"],
                )
                for epoch in data
                if epoch["status"] == "OPEN" and epoch["claimable"]  # Filter condition
            ]

        else:
            raise Exception(f"Request failed with status {response.status_code}")

    except Exception as e:
        raise Exception(f"Error occurred while fetching BSX points: {str(e)}")


def claim_point(start_at: str, end_at: str):
    try:
        api_url = f"{bsx_base_url}/points/claim"
        headers = create_header()

        data = {"start_at": start_at, "end_at": end_at}
        response = requests.post(api_url, headers=headers, json=data)

        if response.status_code == 200:
            return True
        return False

    except Exception as e:
        raise Exception(f"Error occurred while claiming BSX points: {str(e)}")


def get_funding_history(
    product_id: str = "ETH-PERP",
    start_time: int = 0,
    end_time: int = None,
    limit: int = 24,
) -> List[FundingHistoryEntry]:
    params = {
        "from": start_time,
        "to": end_time,
        "limit": limit,
    }
    headers = {"accept": "application/json"}

    try:
        api_url = f"{bsx_base_url}/products/{product_id}/funding-rate"
        response = requests.get(f"{api_url}", headers=headers, params=params)
        response.raise_for_status()  # Raise HTTPError for bad responses
        data = response.json()

        funding_history = data.get("items", [])
        if funding_history:
            # Map the raw funding history to FundingHistoryEntry instances
            return [
                FundingHistoryEntry(
                    datetime=nanoseconds_to_datetime(int(entry["time"])),
                    funding_rate=float(entry["rate"]),
                )
                for entry in funding_history
            ]

        return []

    except requests.RequestException as e:
        print(f"Error BSX fetching funding history: {e}")
        return []
