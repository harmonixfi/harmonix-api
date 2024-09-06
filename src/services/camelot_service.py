import requests
from core.config import settings

WST_ETH_Address = "0xdEb89DE4bb6ecf5BFeD581EB049308b52d9b2Da7"

USDe_USDC_Address = "0xc23f308CF1bFA7efFFB592920a619F00990F8D74"


def get_apy() -> float:
    url = f"{settings.CAMELOT_EXCHANGE_API_URL}/v2/liquidity-v3-data?chainId=42161"
    response = requests.get(url)

    if response.status_code != 200:
        raise Exception(f"Request failed with status {response.status_code}")

    data = response.json()

    apy_data = data["data"]["pools"][WST_ETH_Address]
    market_apr = round(float(apy_data["merkl"]["apr"]), 2)
    swap_fees_apr = round(float(apy_data["activeTvlAverageAPR"]), 2)
    return market_apr + swap_fees_apr


def get_apy_usdc() -> float:
    url = f"{settings.CAMELOT_EXCHANGE_API_URL}/v2/liquidity-v3-data?chainId=42161"
    response = requests.get(url)

    if response.status_code != 200:
        raise Exception(f"Request failed with status {response.status_code}")

    data = response.json()

    apy_data = data["data"]["pools"][USDe_USDC_Address]
    market_apr = round(float(apy_data["merkl"]["apr"]), 2)
    swap_fees_apr = round(float(apy_data["activeTvlAverageAPR"]), 2)
    return market_apr + swap_fees_apr
