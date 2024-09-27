import requests
from web3 import Web3
from core.abi_reader import read_abi
from core.config import settings
from schemas.gold_link_account_holdings import GoldLinkAccountHoldings

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


if __name__ == "__main__":

    print(get_meta_data())

    # Tính loss
    print("Is Liquidatable:")
