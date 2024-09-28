import requests
from web3 import Web3
from core.abi_reader import read_abi
from core.config import settings
from schemas.gold_link_account_holdings import GoldLinkAccountHoldings
from eth_abi import encode

url = settings.GOLD_LINK_API_URL
gold_link_web3_url = "https://bitter-wandering-feather.arbitrum-mainnet.quiknode.pro/862a558ad28be94cf6b1ccae509bdca74a19086a"
w3 = Web3(
    Web3.HTTPProvider(
        "https://bitter-wandering-feather.arbitrum-mainnet.quiknode.pro/862a558ad28be94cf6b1ccae509bdca74a19086a"
    )
)
STRATEGY_RESERVE_ABI_NAME = "strategy-reserve"
STRATEGY_BANK_ABI_NAME = "strategy-bank"
STRATEGY_ACCOUNT_ABI_NAME = "strategy-account"

trading_address = Web3.to_checksum_address("0x04df99681dd2c0d26598139afd517142430b1202")


def get_contract(address, abi_name):
    abi = read_abi(abi_name)
    return w3.eth.contract(address=address, abi=abi)


def get_strategy_bank(strategy_reserve):
    return strategy_reserve.functions.STRATEGY_BANK().call()


def get_account_holdings(strategy_bank, trading_address, decimals=1e6):
    account_holdings = strategy_bank.functions.getStrategyAccountHoldings(
        trading_address
    ).call()

    if not account_holdings:
        return GoldLinkAccountHoldings(collateral=0.0, loan=0.0, interestIndexLast=0.0)

    return GoldLinkAccountHoldings(
        collateral=float(account_holdings[0]) / decimals,
        loan=float(account_holdings[1]) / decimals,
        interest_index_last=float(account_holdings[2]) / decimals,
    )


def get_account_value(strategy_account, decimals=1e6):
    return strategy_account.functions.getAccountValue().call() / decimals


def get_account_holdings_with_interest(strategy_bank, trading_address, decimals=1e6):
    account_holdings_with_interest = (
        strategy_bank.functions.getStrategyAccountHoldingsAfterPayingInterest(
            trading_address
        ).call()
    )
    if not account_holdings_with_interest:
        return GoldLinkAccountHoldings(collateral=0.0, loan=0.0, interestIndexLast=0.0)

    return GoldLinkAccountHoldings(
        collateral=float(account_holdings_with_interest[0]) / decimals,
        loan=float(account_holdings_with_interest[1]) / decimals,
        interest_index_last=float(account_holdings_with_interest[2]) / decimals,
    )


def get_loss():
    # Initialize contracts
    strategy_reserve = get_contract(trading_address, STRATEGY_RESERVE_ABI_NAME)
    strategy_bank = get_contract(
        get_strategy_bank(strategy_reserve), STRATEGY_BANK_ABI_NAME
    )
    strategy_account = get_contract(trading_address, STRATEGY_ACCOUNT_ABI_NAME)

    # Fetch holdings and account value
    account_holdings = get_account_holdings(strategy_bank, trading_address)
    account_value = get_account_value(strategy_account)

    # Calculate loss
    loss = account_holdings.loan - min(account_value, account_holdings.loan)

    return float(loss)


def get_interest() -> float:
    # Initialize contracts
    strategy_reserve = get_contract(trading_address, STRATEGY_RESERVE_ABI_NAME)
    strategy_bank = get_contract(
        get_strategy_bank(strategy_reserve), STRATEGY_BANK_ABI_NAME
    )

    # Fetch holdings and account value
    account_holdings = get_account_holdings(strategy_bank, trading_address)
    account_holdings_with_interest = get_account_holdings_with_interest(
        strategy_bank, trading_address
    )

    interest = account_holdings.collateral - account_holdings_with_interest.collateral
    return interest


def get_health_factor() -> float:
    # Initialize contracts
    strategy_reserve = get_contract(trading_address, STRATEGY_RESERVE_ABI_NAME)
    strategy_bank = get_contract(
        get_strategy_bank(strategy_reserve), STRATEGY_BANK_ABI_NAME
    )

    # Fetch holdings and account value
    account_holdings_with_interest = get_account_holdings_with_interest(
        strategy_bank, trading_address
    )

    account_holdings = get_account_holdings(strategy_bank, trading_address)
    loss = get_loss()
    interest = get_interest()

    health_factor_score = (
        account_holdings_with_interest.collateral - interest - loss
    ) / account_holdings.loan
    return health_factor_score


def get_meta_data():
    # Initialize contracts
    strategy_reserve = get_contract(trading_address, STRATEGY_RESERVE_ABI_NAME)
    strategy_bank = get_contract(
        get_strategy_bank(strategy_reserve), STRATEGY_BANK_ABI_NAME
    )
    strategy_account = get_contract(trading_address, STRATEGY_ACCOUNT_ABI_NAME)

    # Fetch holdings and account value
    account_holdings = get_account_holdings(strategy_bank, trading_address)
    account_holdings_with_interest = get_account_holdings_with_interest(
        strategy_bank, trading_address
    )
    account_value = get_account_value(strategy_account)

    interest = account_holdings.collateral - account_holdings_with_interest.collateral
    loss = account_holdings.loan - min(account_value, account_holdings.loan)
    health_factor_score = (
        account_holdings_with_interest.collateral - interest - loss
    ) / account_holdings.loan

    return {
        "collateral": account_holdings_with_interest.collateral,
        "loss": loss,
        "health_factor_score": health_factor_score,
    }


def get_borrow_apr(
    network_id_mainnet: str = "0xB4E29A1A0E6F9DB584447E988CE15D48A1381311",
    decimals=1e18,
):
    params = f'["{network_id_mainnet}"]'

    api_url = f"{url}/?method=goldlink/getStrategyInfo&params={params}"
    response = requests.get(api_url)

    if response.status_code == 200:
        data = response.json()["result"]

        return float(data.get("borrow_apr", "0")) / decimals
    else:
        raise Exception(f"Request failed with status {response.status_code}")


def get_token_addresses_for_market(market="0xFD70de6b91282D8017aA4E741e9Ae325CAb992d8"):
    """
    Get addresses for market.

    :param market: required
    :type market: address

    :returns: Object
    """
    WETH_USDC = "0x70d95587d40A2caf56bd97485aB3Eec10Bee6336"
    gmx_v2_reader = get_contract(trading_address, "gmx_v2_reader")
    token_addresses = gmx_v2_reader.functions.getMarket(
        "0xFD70de6b91282D8017aA4E741e9Ae325CAb992d8", WETH_USDC
    ).call()

    return {
        "market_token": token_addresses[0],
        "index_token": token_addresses[1],
        "long_token": token_addresses[2],
        "short_token": token_addresses[3],
    }


def get_position_key(strategy_account):
    """
    Get a position's key.

    :param market: required
    :type market: address

    :param strategy_account: required
    :type strategy_account: address

    :returns: str
    """
    market_addresses = get_token_addresses_for_market(
        "0xFD70de6b91282D8017aA4E741e9Ae325CAb992d8"
    )
    return Web3.solidityKeccak(
        ["bytes"],
        [
            encode(
                ["address", "address", "address", "bool"],
                [
                    strategy_account,
                    "0xFD70de6b91282D8017aA4E741e9Ae325CAb992d8",
                    market_addresses["long_token"],
                    False,
                ],
            )
        ],
    ).hex()


if __name__ == "__main__":
    # strategy_account = get_contract(trading_address, STRATEGY_ACCOUNT_ABI_NAME)
    # gmx_v2_reader = get_contract(trading_address, "gmx_v2_reader")
    # position = gmx_v2_reader.functions.getPosition(
    #     "0xFD70de6b91282D8017aA4E741e9Ae325CAb992d8",
    #     get_position_key(strategy_account),
    # ).call()

    # print(get_meta_data())
    print(get_meta_data())

    # Tính loss
    print("Is Liquidatable:")
