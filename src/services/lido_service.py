import requests
from typing import Dict, Any
from core.config import settings


def get_apy() -> float:
    url = f"{settings.LIDO_API_URL}/v1/protocol/steth/apr/sma"
    response = requests.get(url)

    if response.status_code != 200:
        raise Exception(f"Request failed with status {response.status_code}")

    data = response.json()

    apy_data = data["data"]["smaApr"]
    return float(apy_data)
