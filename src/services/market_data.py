from datetime import datetime
import requests


def get_price(symbol):
    url = f"https://api.binance.com/api/v3/avgPrice?symbol={symbol}"
    headers = {"Content-Type": "application/json"}
    response = requests.get(url, headers=headers)
    return float(response.json()["price"])


def get_klines(symbol, start_time: datetime, end_time: datetime, interval="1d", limit=500):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}&startTime={int(start_time.timestamp() * 1000)}&endTime={int(end_time.timestamp() * 1000)}"
    headers = {"Content-Type": "application/json"}
    response = requests.get(url, headers=headers)
    return response.json()
