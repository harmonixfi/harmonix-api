from typing import List
import requests
from core.config import settings
from schemas.pendle_market import PendleMarket

url = settings.PENDLE_API_URL


def get_market(
    chain_id: int, pt_address: str, skipPage: int = 0, limitPage: int = 10
) -> List[PendleMarket]:

    api_url = f"{url}/{chain_id}/markets?order_by=name%3A1&skip={skipPage}&limit={limitPage}&pt={pt_address}"
    response = requests.get(api_url)

    if response.status_code == 200:
        data = response.json()["results"]  # Access the 'results' array
        markets = []
        for market in data:
            market_obj = PendleMarket(
                id=market["id"],
                chainId=market["chainId"],
                symbol=market["symbol"],
                expiry=market["expiry"],
                underlyingInterestApy=market.get("underlyingInterestApy", 0.0),
                impliedApy=market.get("impliedApy", 0.0),
                ptDiscount=market.get("ptDiscount", 0.0),
            )
            markets.append(market_obj)

        return markets
    else:
        raise Exception(f"Request failed with status {response.status_code}")
