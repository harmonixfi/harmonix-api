import requests
from web3 import Web3
from core.abi_reader import read_abi
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


if __name__ == "__main__":

    w3 = Web3(
        Web3.HTTPProvider(
            "https://bitter-wandering-feather.arbitrum-mainnet.quiknode.pro/862a558ad28be94cf6b1ccae509bdca74a19086a"
        )
    )

    strategy_account_address = Web3.to_checksum_address(
        "0x04df99681dd2c0d26598139afd517142430b1202"
    )

    strategy_reserve_abi = read_abi("strategy-reserve")
    strategy_reserve = w3.eth.contract(
        address=strategy_account_address,
        abi=strategy_reserve_abi,
    )

    bank = strategy_reserve.functions.STRATEGY_BANK().call()
    print("bank", bank)

    bank_abi = read_abi("strategy-bank")
    strategy_bank = w3.eth.contract(
        address=bank,
        abi=bank_abi,
    )

    strategy_account_abi = read_abi("strategy-account")
    strategy_account = w3.eth.contract(
        address=strategy_account_address,
        abi=strategy_account_abi,
    )
    account_value = strategy_account.functions.getAccountValue().call()
    print("account_value", account_value)

    holdings_after_pay_interest = (
        strategy_bank.functions.getStrategyAccountHoldingsAfterPayingInterest(
            strategy_account_address,
        ).call()
    )
    print(
        {
            "collateral": holdings_after_pay_interest[0] / 1e6,
            "loan": holdings_after_pay_interest[1],
            "interestIndexLast": holdings_after_pay_interest[2],
        }
    )
    health_factor = account_value / holdings_after_pay_interest[1]
    healthScore = (holdings_after_pay_interest[0]) / holdings_after_pay_interest[1]
    print("healthScore", health_factor)
    liquidatable_health_score = (
        strategy_bank.functions.LIQUIDATABLE_HEALTH_SCORE().call()
    )

    initial_value = -176.111683
    holdings = strategy_bank.functions.getStrategyAccountHoldingsAfterPayingInterest(
        strategy_account.address
    ).call()
    collateral = holdings[0] / 1e6
    loan = holdings[1] / 1e6

    # Tính equity
    equity = collateral - loan

    # Tính loss
    loss = max(initial_value - equity, 0)
    print("Is Liquidatable:", loss)
