from datetime import datetime, timezone
from typing import List
import requests
from core.config import settings
from schemas.bsx_point import BSXPoint

api_key = settings.BSX_API_KEY
secret = settings.BSX_SECRET
bsx_base_url = settings.BSX_BASE_API_URL


def get_points_earned() -> float:
    headers = {
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

    response = requests.get(f"{bsx_base_url}/points/trading", headers=headers)

    if response.status_code == 200:
        data = response.json()
        total = data.get("total_points_earned")
        return float(total) if total is not None else 0.0
    else:
        raise Exception(f"Request failed with status {response.status_code}")


def get_list_claim_bsx_point() -> List[BSXPoint]:
    try:
        api_url = f"{bsx_base_url}/points/trading"
        headers = {
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

        response = requests.get(api_url, headers=headers)

        if response.status_code == 200:
            data = response.json()["epochs"]
            return [
                BSXPoint(
                    start_at=datetime.fromtimestamp(
                        int(epoch["start_at"]) / 1e9, tz=timezone.utc
                    ),
                    end_at=datetime.fromtimestamp(
                        int(epoch["end_at"]) / 1e9, tz=timezone.utc
                    ),
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
            ]
        else:
            raise Exception(f"Request failed with status {response.status_code}")

    except Exception as e:
        raise Exception(f"Error occurred while fetching BSX points: {str(e)}")


def claim_bsx_point():
    try:
        # Giả sử API endpoint để claim point
        api_url = f"{bsx_base_url}/v1/claim-point"
        headers = {
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

        response = requests.post(api_url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            claimed_points = data.get("claimed_points", 0)

    except Exception as e:
        raise Exception(f"Error occurred while claiming BSX points: {str(e)}")
