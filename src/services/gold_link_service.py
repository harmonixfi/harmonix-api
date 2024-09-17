import requests
from core.config import settings

url = settings.GOLD_LINK_API_URL


def __convert_to_float(value, divisor=1e18):
    """Child method to convert large integer values to float and divide by a divisor."""
    return float(value) / divisor


def get_strategy_info():
    params = {
        "method": "goldlink/getStrategyInfo",
        "params": ["0xb4e29a1a0e6f9db584447e988ce15d48a1381311"],
        "jsonrpc": "2.0",
        "id": "1",
    }

    response = requests.post(url, json=params)

    if response.status_code == 200:
        data = response.json()
        result = data.get("result", {})

        # Using the convert_to_float method to process supply_apy and borrow_apr
        supply_apy = __convert_to_float(result.get("supply_apy", 0), 1e18)
        borrow_apr = __convert_to_float(result.get("borrow_apr", 0), 1e18)

        reserve_balance = result.get("reserve_balance")
        utilized = result.get("utilized")

        # Returning the extracted and processed data
        return {
            "supply_apy": supply_apy,
            "borrow_apr": borrow_apr,
            "reserve_balance": reserve_balance,
            "utilized": utilized,
        }
    else:
        return {"error": f"Failed to fetch data. Status code: {response.status_code}"}


def get_account_positions():
    params = {
        "method": "goldlink/getAccountPositions",
        "params": ["0x04df99681dd2c0d26598139afd517142430b1202"],
        "jsonrpc": "2.0",
        "id": "1",
    }

    response = requests.post(url, json=params)

    if response.status_code == 200:
        data = response.json()
        result = data.get("result", [])

        positions = []

        for position in result:
            # Process each position and divide relevant fields by 1e18
            account = position.get("account")
            market = position.get("market")
            block = position.get("block")
            ts = position.get("ts")
            collateral_token = position.get("collateral_token")
            size_in_usd = __convert_to_float(position.get("size_in_usd"))
            size_in_tokens = __convert_to_float(position.get("size_in_tokens"))
            collateral_amount = __convert_to_float(position.get("collateral_amount"))
            borrowing_factor = __convert_to_float(position.get("borrowing_factor"))
            funding_fee_amount_per_size = __convert_to_float(
                position.get("funding_fee_amount_per_size")
            )
            long_token_claimable_funding_amount_per_size = __convert_to_float(
                position.get("long_token_claimable_funding_amount_per_size")
            )
            short_token_claimable_funding_amount_per_size = __convert_to_float(
                position.get("short_token_claimable_funding_amount_per_size")
            )
            index_token_price_max = __convert_to_float(
                position.get("index_token_price_max")
            )
            collateral_token_price_max = __convert_to_float(
                position.get("collateral_token_price_max")
            )
            position_key = position.get("position_key")

            # Append the processed position to the list
            positions.append(
                {
                    "account": account,
                    "market": market,
                    "block": block,
                    "timestamp": ts,
                    "collateral_token": collateral_token,
                    "size_in_usd": size_in_usd,
                    "size_in_tokens": size_in_tokens,
                    "collateral_amount": collateral_amount,
                    "borrowing_factor": borrowing_factor,
                    "funding_fee_amount_per_size": funding_fee_amount_per_size,
                    "long_token_claimable_funding_amount_per_size": long_token_claimable_funding_amount_per_size,
                    "short_token_claimable_funding_amount_per_size": short_token_claimable_funding_amount_per_size,
                    "index_token_price_max": index_token_price_max,
                    "collateral_token_price_max": collateral_token_price_max,
                    "position_key": position_key,
                }
            )

        return positions
    else:
        return {"error": f"Failed to fetch data. Status code: {response.status_code}"}
