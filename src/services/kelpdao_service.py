import requests
from typing import Dict, Any
from core.config import settings
from schemas import EarnedRestakingPoints
from core import constants


def get_points(user_address: str) -> EarnedRestakingPoints:
    url = f"{settings.KELPDAO_BASE_API_URL}km-el-points/user/{user_address}"
    headers = {"Accept-Encoding": "gzip"}
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise Exception(f"Request failed with status {response.status_code}")

    data = response.json()

    point_res = data["value"]
    return EarnedRestakingPoints(
        wallet_address=user_address,
        total_points=float(point_res["kelpMiles"]),
        eigen_layer_points=float(point_res["elPoints"]),
        partner_name=constants.KELPDAO,
    )


def get_apy() -> float:
    url = f"{settings.KELPDAO_API_URL}/rseth/apy"
    response = requests.get(url)

    if response.status_code != 200:
        raise Exception(f"Request failed with status {response.status_code}")

    data = response.json()

    apy_data = data["value"]
    return float(apy_data)


# Usage:
# points = get_points('0xBC05da14287317FE12B1a2b5a0E1d756Ff1801Aa')
# print(points)
