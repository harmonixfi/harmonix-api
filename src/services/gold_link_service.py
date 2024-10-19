import requests
from web3 import Web3
from core.abi_reader import read_abi
from core.config import settings
from schemas.gold_link_account_holdings import GoldLinkAccountHoldings

url = settings.GOLD_LINK_API_URL

STRATEGY_RESERVE_ABI_NAME = "strategy-reserve"
STRATEGY_BANK_ABI_NAME = "strategy-bank"
STRATEGY_ACCOUNT_ABI_NAME = "strategy-account"


def get_trading_address(trading_account: str):
    return Web3.to_checksum_address(trading_account)


def get_contract(address, abi_name, web3: Web3):
    abi = read_abi(abi_name)
    return web3.eth.contract(address=address, abi=abi)


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


def get_health_factor_score(trading_account: str) -> float:
    # Initialize contracts
    web3 = Web3(Web3.HTTPProvider(settings.ARBITRUM_MAINNET_INFURA_URL))
    trading_address = get_trading_address(trading_account)

    strategy_reserve = get_contract(trading_address, STRATEGY_RESERVE_ABI_NAME, web3)
    strategy_bank = get_contract(
        get_strategy_bank(strategy_reserve), STRATEGY_BANK_ABI_NAME, web3
    )
    strategy_account = get_contract(trading_address, STRATEGY_ACCOUNT_ABI_NAME, web3)

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

    return health_factor_score


def get_borrow_apr(
    decimals=1e18,
):
    params = f'["{settings.GOLD_LINK_NETWORK_ID_MAINNET}"]'

    api_url = f"{url}/?method=goldlink/getStrategyInfo&params={params}"
    response = requests.get(api_url)

    if response.status_code == 200:
        data = response.json()["result"]

        return float(data.get("borrow_apr", "0")) / decimals
    else:
        raise Exception(f"Request failed with status {response.status_code}")


def get_position_size(
    trading_account: str,
    decimals=1e18,
):
    params = f'["{trading_account}"]'

    api_url = f"{url}/?method=goldlink/getAccountPositions&params={params}"
    response = requests.get(api_url)

    if response.status_code == 200:
        size_in_tokens = 0
        data = response.json()["result"]
        for item in data:
            size_in_tokens += float(item["size_in_tokens"]) / decimals

        return size_in_tokens
    else:
        raise Exception(f"Request failed with status {response.status_code}")
