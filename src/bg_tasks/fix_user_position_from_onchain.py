"""
Query all UserPorfolio join with Vaults:
- get vault_contract using get_vault_contract function
- define get_user_state function to get user state from onchain using getUserVaultState function, getUserVaultState will return 4 values in tupple: deposit_amount, shares, profit, loss
- define get_pps function to get price per share from onchain using pricePerShare function
- calculate following information:
totalBalance = shares * pps

- update user position with following information:
- deposit_amount
- shares
- totalBalance


"""

from datetime import datetime, timedelta, timezone
from sqlalchemy import func
from sqlmodel import Session, select
from web3 import Web3
from web3.contract import Contract

from core import constants
from core.abi_reader import read_abi
from core.db import engine
from models.onchain_transaction_history import OnchainTransactionHistory
from models.user_portfolio import PositionStatus, UserPortfolio
from models.vaults import Vault
from services.vault_contract_service import VaultContractService

session = Session(engine)


def get_vault_contract(vault: Vault, contract_abi_name) -> tuple[Contract, Web3]:
    w3 = Web3(Web3.HTTPProvider(constants.NETWORK_RPC_URLS[vault.network_chain]))

    rockonyx_delta_neutral_vault_abi = read_abi(contract_abi_name)
    vault_contract = w3.eth.contract(
        address=vault.contract_address,
        abi=rockonyx_delta_neutral_vault_abi,
    )
    return vault_contract, w3


def get_user_state(
    vault_contract: Contract, user_address: str
) -> tuple[int, int, int, int]:

    user_state = vault_contract.functions.getUserVaultState().call(
        {"from": Web3.to_checksum_address(user_address)}
    )
    return user_state


def get_pending_withdrawal_shares(
    vault_contract: Contract, user_address: str
) -> tuple[int, int, int, int]:

    user_state = vault_contract.functions.getUserWithdrawlShares().call(
        {"from": Web3.to_checksum_address(user_address)}
    )
    return user_state


def get_pps(vault_contract: Contract) -> int:
    pps = vault_contract.functions.pricePerShare().call()
    return pps


def fix_user_position_for_vault(vault: Vault):
    abi_name = (
        "rockonyxdeltaneutralvault"
        if vault.strategy_name == constants.DELTA_NEUTRAL_STRATEGY
        else "rockonyxstablecoin"
    )
    vault_contract, w3 = get_vault_contract(vault, abi_name)

    user_positions = session.exec(
        select(UserPortfolio)
        .where(UserPortfolio.vault_id == vault.id)
        .where(UserPortfolio.status == PositionStatus.ACTIVE)
    ).all()

    for user_portfolio in user_positions:
        user_state = get_user_state(vault_contract, user_portfolio.user_address)
        pps = get_pps(vault_contract)
        total_balance = (user_state[1] * pps) / 1e12
        user_portfolio.init_deposit = user_state[0] / 1e6
        user_portfolio.total_shares = user_state[1] / 1e6
        user_portfolio.total_balance = total_balance

        pending_withdrawal = get_pending_withdrawal_shares(
            vault_contract, user_portfolio.user_address
        )
        user_portfolio.pending_withdrawal = pending_withdrawal / 1e6

        session.add(user_portfolio)
        session.commit()
        print(f"User {user_portfolio.user_address} position updated")

    print(f"Vault {vault.contract_address} user positions updated")


def fix_user_position_by_address(vault: Vault, user_address: str):
    user_portfolio = session.exec(
        select(UserPortfolio)
        .where(UserPortfolio.user_address == user_address.lower())
        .where(UserPortfolio.vault_id == vault.id)
        .where(UserPortfolio.status == PositionStatus.ACTIVE)
    ).first()

    abi_name = (
        "rockonyxdeltaneutralvault"
        if vault.strategy_name == constants.DELTA_NEUTRAL_STRATEGY
        else "rockonyxstablecoin"
    )
    vault_contract, w3 = get_vault_contract(vault, abi_name)

    user_state = get_user_state(vault_contract, user_address)
    pps = get_pps(vault_contract)
    total_balance = (user_state[1] * pps) / 1e12

    pending_withdrawal = get_pending_withdrawal_shares(vault_contract, user_address)
    if user_portfolio is None:
        user_portfolio = UserPortfolio(
            vault_id=vault.id,
            user_address=user_address,
            init_deposit=user_state[0] / 1e6,
            total_shares=user_state[1] / 1e6,
            total_balance=total_balance,
            pending_withdrawal=pending_withdrawal / 1e6,
        )
    else:
        user_portfolio.init_deposit = user_state[0] / 1e6
        user_portfolio.total_shares = user_state[1] / 1e6
        user_portfolio.total_balance = total_balance
        user_portfolio.pending_withdrawal = pending_withdrawal / 1e6

    session.add(user_portfolio)
    session.commit()


def main():
    # vaults = session.exec(
    #     select(Vault).where(Vault.strategy_name == constants.DELTA_NEUTRAL_STRATEGY)
    # ).all()
    # for vault in vaults:
    #     fix_user_position_for_vault(vault)

    vault_contract_service = VaultContractService()
    three_days_ago_timestamp = int(
        (datetime.now(tz=timezone.utc) - timedelta(days=3)).timestamp()
    )
    subquery = (
        select(
            OnchainTransactionHistory.from_address,
            func.max(OnchainTransactionHistory.timestamp).label("max_timestamp"),
        )
        .where(OnchainTransactionHistory.timestamp >= three_days_ago_timestamp)
        .group_by(OnchainTransactionHistory.from_address)
        .subquery()
    )
    deposits_query = (
        select(OnchainTransactionHistory)
        .where(
            OnchainTransactionHistory.method_id.in_(
                [
                    constants.MethodID.DEPOSIT2.value,
                    constants.MethodID.DEPOSIT.value,
                    constants.MethodID.DEPOSIT3.value,
                ]
            )
        )
        .join(
            subquery,
            (OnchainTransactionHistory.from_address == subquery.c.from_address)
            & (OnchainTransactionHistory.timestamp == subquery.c.max_timestamp),
        )
    )

    deposits = session.exec(deposits_query).all()

    for deposit in deposits:
        
        user_portfolio = session.exec(
            select(UserPortfolio)
            .where(UserPortfolio.user_address.lower() == deposit.from_address.lower())
            .where(UserPortfolio.status == PositionStatus.ACTIVE)
        ).first()
        
        if user_portfolio is None:
            
        
    # vault = session.exec(
    #     select(Vault).where(Vault.id == "65f75bd7-a2d2-4764-ae31-78e4bb132c62")
    # ).first()

    # fix_user_position_by_address(
    #     vault, "0x864608EFC402E4714b07BC52a49120FF74387a0B".lower()
    # )


if __name__ == "__main__":
    main()
