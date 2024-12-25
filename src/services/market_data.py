from datetime import datetime
import requests


def get_price(symbol):
    url = f"https://api.binance.com/api/v3/avgPrice?symbol={symbol}"
    headers = {"Content-Type": "application/json"}
    response = requests.get(url, headers=headers)
    return float(response.json()["price"])


def get_hl_price(symbol: str) -> float:
    """Get mid price from HyperLiquid L2 order book.

    Args:
        symbol: Trading pair symbol (e.g., 'HYPE')

    Returns:
        float: Mid price between best bid and best ask

    Raises:
        requests.RequestException: If API request fails
        ValueError: If response format is invalid or no price data
    """
    url = "https://api-ui.hyperliquid.xyz/info"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    }
    payload = {"type": "l2Book", "coin": symbol}

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

        if not data.get("levels") or len(data["levels"]) != 2:
            raise ValueError("Invalid order book data format")

        # levels[0] contains bids, levels[1] contains asks
        best_bid = float(data["levels"][0][0]["px"])  # First bid price
        best_ask = float(data["levels"][1][0]["px"])  # First ask price

        # Calculate mid price
        mid_price = (best_bid + best_ask) / 2

        return mid_price

    except requests.RequestException as e:
        raise requests.RequestException(f"Failed to fetch HyperLiquid price: {str(e)}")
    except (KeyError, IndexError, ValueError) as e:
        raise ValueError(f"Failed to parse HyperLiquid price data: {str(e)}")


def get_klines(
    symbol, start_time: datetime, end_time: datetime, interval="1d", limit=500
):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}&startTime={int(start_time.timestamp() * 1000)}&endTime={int(end_time.timestamp() * 1000)}"
    headers = {"Content-Type": "application/json"}
    response = requests.get(url, headers=headers)
    return response.json()
