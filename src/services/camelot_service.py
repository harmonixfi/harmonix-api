import requests
from core.config import settings


def get_pool_apy(pool_addres: str, chain_id: int = 42161) -> float:
    url = f"{settings.CAMELOT_EXCHANGE_API_URL}/v2/liquidity-v3-data?chainId={chain_id}"
    response = requests.get(url)

    if response.status_code != 200:
        raise Exception(f"Request failed with status {response.status_code}")

    data = response.json()

    apy_data = data["data"]["pools"][pool_addres]
    market_apr = round(float(apy_data["merkl"]["apr"]), 2)
    swap_fees_apr = round(float(apy_data["activeTvlAverageAPR"]), 2)
    return market_apr + swap_fees_apr
