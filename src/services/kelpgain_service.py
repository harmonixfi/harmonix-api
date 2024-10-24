import requests
from typing import Dict, Any
from core.config import settings
from schemas import EarnedRestakingPoints
from core import constants

WALLET_ADDRESS = "0xe1B4d34E8754600962Cd944B535180Bd758E6c2e"


def get_points(user_address: str) -> EarnedRestakingPoints:
    url = f"{settings.KELPGAIN_BASE_API_URL}gain/user/{user_address}"
    headers = {"Accept-Encoding": "gzip"}
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise Exception(f"Request failed with status {response.status_code}")

    data = response.json()

    point_res = data[WALLET_ADDRESS]
    return EarnedRestakingPoints(
        wallet_address=user_address,
        total_points=float(point_res["km"]),
        eigen_layer_points=float(point_res["el"]),
        partner_name=constants.KELPDAO,
        scroll_points=float(point_res["scrollPoints"]),
        karak_points=float(point_res["karakPoints"]),
        linea_points=float(point_res["lineaPoints"]),
    )


def get_apy() -> float:
    url = f"{settings.KELPDAO_API_URL}/rseth/apy"
    response = requests.get(url)

    if response.status_code != 200:
        raise Exception(f"Request failed with status {response.status_code}")

    data = response.json()

    apy_data = data["value"]
    return float(apy_data)
