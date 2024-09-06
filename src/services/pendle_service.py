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


def get_user_points():
    url = "https://api-ui.hyperliquid.xyz/info"

    headers = {
        "authority": "api-ui.hyperliquid.xyz",
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,vi;q=0.8",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "origin": "https://app.hyperliquid.xyz",
        "pragma": "no-cache",
        "referer": "https://app.hyperliquid.xyz/",
        "sec-ch-ua": '"Not_A Brand";v="99", "Google Chrome";v="109", "Chromium";v="109"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    }

    data = {
        "signature": {
            "r": "0x3459ec392736749e9b0118b298be049173a3752fe07966efec84d973c1540934",
            "s": "0x5d3f866b1eb0d679784882e8d0f8f5e5076a9aca95f889ac5adb86ca711ebbb5",
            "v": 28,
        },
        "timestamp": 1725622234,
        "type": "userPoints",
        "user": "0x4328Ed031d6A750ff278bd80B01A9045faE4be38",
    }

    response = requests.post(url, headers=headers, json=data)

    # Check if the request was successful
    if response.status_code == 200:
        return response.json()
    else:
        return {"error": f"Request failed with status code {response.status_code}"}
