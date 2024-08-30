from typing import List
import requests
from core.config import settings
from schemas.pendle_market import PendleMarket

url = settings.PENDLE_API_URL


def get_market(
    chain_id: int, pt_address: str, skip_page: int = 0, limit_page: int = 10
) -> List[PendleMarket]:

    api_url = f"{url}/{chain_id}/markets?order_by=name%3A1&skip={skip_page}&limit={limit_page}&pt={pt_address}"
    response = requests.get(api_url)

    if response.status_code == 200:
        data = response.json()["results"]  # Access the 'results' array
        markets = []
        for market in data:
            market_mapper = PendleMarket(
                id=market["id"],
                chain_id=market["chainId"],
                symbol=market["symbol"],
                expiry=market["expiry"],
                underlying_interest_apy=market.get("underlyingInterestApy", 0.0),
                implied_apy=market.get("impliedApy", 0.0),
                pt_discount=market.get("ptDiscount", 0.0),
            )
            markets.append(market_mapper)

        return markets
    else:
        raise Exception(f"Request failed with status {response.status_code}")
