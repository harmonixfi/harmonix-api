import requests
from typing import Dict, Any
from core.config import settings
from schemas import EarnedRestakingPoints
from core import constants

headers = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
    "Referer": "https://stake.zircuit.com/?ref=renzoo",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


def get_points(user_address: str) -> EarnedRestakingPoints:
    url = f"{settings.ZIRCUIT_BASE_API_URL}portfolio/{user_address}"

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise Exception(f"Request failed with status {response.status_code}")

    data = response.json()

    total_points = sum(
        float(item["points"])
        for sublist in data.values()
        for item in sublist
        if "points" in item
    )

    return EarnedRestakingPoints(
        wallet_address=user_address,
        total_points=total_points,
        partner_name=constants.ZIRCUIT,
    )


# Usage:
# points = get_points('0xBC05da14287317FE12B1a2b5a0E1d756Ff1801Aa')
# print(points)
