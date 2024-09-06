import requests
from typing import Dict, Any
from core.config import settings
from schemas import EarnedRestakingPoints
from core import constants


def get_points(user_address: str) -> EarnedRestakingPoints:
    url = f"{settings.RENZO_BASE_API_URL}points/{user_address}"
    headers = {"Accept-Encoding": "gzip"}
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise Exception(f"Request failed with status {response.status_code}")

    data = response.json()

    if not data["success"]:
        raise Exception("Renzo service returned an error")

    point_res = data["data"]["totals"]
    return EarnedRestakingPoints(
        wallet_address=user_address,
        total_points=point_res["renzoPoints"],
        eigen_layer_points=point_res["eigenLayerPoints"],
        partner_name=constants.RENZO,
    )


def get_apy() -> float:
    url = f"{settings.RENZO_API_URL}"
    response = requests.get(url)

    if response.status_code != 200:
        raise Exception(f"Request failed with status {response.status_code}")

    try:
        data = response.json()
        apy_data = data["data"]["apr"]["data"]["rate"]
        return float(apy_data)
    except (KeyError, TypeError, ValueError) as e:
        raise Exception(f"Error parsing APY data: {e}")


# Usage:
# points = get_points('0xBC05da14287317FE12B1a2b5a0E1d756Ff1801Aa')
# print(points)
