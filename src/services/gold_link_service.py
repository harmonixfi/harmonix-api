from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List
import uuid
import requests
from sqlmodel import Session, select
from web3 import Web3
from core import constants
from core.abi_reader import read_abi
from core.config import settings
from models.vault_rewards import VaultRewards
from models.vaults import Vault
from schemas.funding_history_entry import FundingHistoryEntry
from schemas.gold_link_account_holdings import GoldLinkAccountHoldings
from utils.vault_utils import nanoseconds_to_datetime

url = settings.GOLD_LINK_API_URL

STRATEGY_RESERVE_ABI_NAME = "strategy-reserve"
STRATEGY_BANK_ABI_NAME = "strategy-bank"
STRATEGY_ACCOUNT_ABI_NAME = "strategy-account"

STRATEGY_RESERVE_ADDRESS = "0xd8dd54df1a7d2ea022b983756d8a481eea2a382a"


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


def __get_contract(vault: Vault, abi_name="goldlink_rewards"):
    web3 = Web3(Web3.HTTPProvider(constants.NETWORK_RPC_URLS[vault.network_chain]))

    abi = read_abi(abi_name)
    return web3.eth.contract(address=settings.GOLDLINK_REWARD_CONTRACT_ADDRESS, abi=abi)


def get_current_rewards_earned(
    vault: Vault, abi_name="goldlink_rewards", decimals=1e18
) -> float:
    try:
        contract = __get_contract(vault, abi_name)
        return float(
            contract.functions.rewardsOwed(
                Web3.to_checksum_address(vault.contract_address)
            ).call()
            / decimals
        )
    except Exception:
        return 0.0


def get_funding_history(decimals=1e30) -> List[FundingHistoryEntry]:
    headers = {"accept": "application/json"}
    params = f'["{settings.GOLD_LINK_ETH_NETWORK_ID_MAINNET}",20]'
    api_url = f"{url}/?method=goldlink/getGmxHistoricFundingRate&params={params}"

    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        data = response.json()

        funding_history = data.get("result", [])
        return [
            FundingHistoryEntry(
                datetime=entry["ts"],
                funding_rate=float(entry["funding_rate"]) / decimals,
            )
            for entry in funding_history
        ]
    except requests.exceptions.RequestException as e:
        print(f"Error fetching funding history: {e}")
        return []


def get_apy_rate_history(
    decimals: float = 1e18, start_timestamp: int = 0, end_timestamp: int = -1
) -> List[Dict[datetime, float]]:
    headers = {"accept": "application/json"}
    params = f'["{STRATEGY_RESERVE_ADDRESS}",{start_timestamp},{end_timestamp}]'
    api_url = f"{url}/?method=goldlink/getHistoricReserveInterestRate&params={params}"

    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        data = response.json()

        funding_history = data.get("result", [])
        return [
            {
                datetime.strptime(entry["timestamp"], "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=timezone.utc
                ): float(entry["apy"])
                / decimals,
            }
            for entry in funding_history
        ]
    except requests.exceptions.RequestException as e:
        print(f"Error fetching apy rate history: {e}")
        return []
