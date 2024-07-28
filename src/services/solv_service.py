import requests
import json
from datetime import datetime, timezone
import pandas as pd
from bg_tasks.utils import calculate_roi
from core.config import settings


def nav_data_to_dataframe(nav_data):
    df = pd.DataFrame(nav_data)
    df["navDate"] = pd.to_datetime(df["navDate"])
    df["nav"] = df["nav"].astype(float) / 1e8  # Adjust for currency decimals
    df["adjustedNav"] = df["adjustedNav"].astype(float) / 1e8  # Adjust for currency decimals
    return df[["navDate", "nav", "adjustedNav"]]


def fetch_nav_data():
    url = "https://sft-api.com/graphql"
    payload = '{"query":"query NavsOpenFund($filter: NavOpenFundFilter, $pagination: Pagination, $sort: Sort) {\\n  navsOpenFund(filter: $filter, pagination: $pagination, sort: $sort) {\\n    poolSlotInfoId\\n    symbol\\n    allTimeHigh\\n    currencyDecimals\\n    serialData {\\n      nav\\n      navDate\\n      adjustedNav\\n      __typename\\n    }\\n    __typename\\n  }\\n}","variables":{"filter":{"navType":"Investment","poolSlotInfoId":40},"pagination":{},"sort":{"field":"navDate","direction":"ASC"}}}'
    headers = {
        "authority": "sft-api.com",
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,vi;q=0.8",
        "authorization": settings.SOLV_API_KEY,
        "cache-control": "no-cache",
        "content-type": "application/json",
        "origin": "https://app.solv.finance",
        "pragma": "no-cache",
        "referer": "https://app.solv.finance/",
        "sec-ch-ua": '"Not_A Brand";v="99", "Google Chrome";v="109", "Chromium";v="109"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
        "x-amz-user-agent": "aws-amplify/3.0.7",
    }

    response = requests.post(url, headers=headers, data=payload)
    if response.status_code == 200:
        data = response.json()
        if "data" in data and "navsOpenFund" in data["data"]:
            nav_data = data["data"]["navsOpenFund"]["serialData"]
            df = nav_data_to_dataframe(nav_data)
            return df
    return None


def get_monthly_apy(df, column="nav"):
    now = pd.Timestamp.now(tz="UTC")
    one_month_ago = now - pd.DateOffset(months=1)
    recent_nav = df[df["navDate"] <= now.strftime("%Y-%m-%d")].iloc[-1][column]
    month_ago_nav = df[df["navDate"] <= one_month_ago.strftime("%Y-%m-%d")].iloc[-1][
        column
    ]
    days = (now - one_month_ago).days
    return calculate_roi(recent_nav, month_ago_nav, days)


def get_weekly_apy(df, column="nav"):
    now = pd.Timestamp.now(tz="UTC")
    one_week_ago = now - pd.DateOffset(weeks=1)
    recent_nav = df[df["navDate"] <= now.strftime("%Y-%m-%d")].iloc[-1][column]
    week_ago_nav = df[df["navDate"] <= one_week_ago.strftime("%Y-%m-%d")].iloc[-1][
        column
    ]
    days = (now - one_week_ago).days
    return calculate_roi(recent_nav, week_ago_nav, days)


if __name__ == "__main__":
    nav_data = fetch_nav_data()
    df = nav_data_to_dataframe(nav_data)
    print("Monthly APY:", get_monthly_apy(df))
    print("Weekly APY:", get_weekly_apy(df))
