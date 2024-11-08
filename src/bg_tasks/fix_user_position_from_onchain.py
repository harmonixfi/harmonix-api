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
import logging
from sqlalchemy import func
from sqlmodel import Session, select
from web3 import Web3
from web3.contract import Contract

from core import constants
from core.abi_reader import read_abi
from core.db import engine
from log import setup_logging_to_console
from models.onchain_transaction_history import OnchainTransactionHistory
from models.user_portfolio import PositionStatus, UserPortfolio
from models.vaults import Vault
from services.vault_contract_service import VaultContractService
import time

session = Session(engine)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fix_user_position_from_onchain")


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


def get_recent_deposits_query(subquery):
    return (
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


def fetch_vault(deposit, vault_contract_service):
    vault_address = vault_contract_service.get_vault_address_by_contract(
        deposit.to_address.lower()
    )
    return session.exec(
        select(Vault).where(
            func.lower(Vault.contract_address).in_(
                func.lower(addr) for addr in vault_address
            )
        )
    ).first()


def get_user_portfolio_data(vault_contract, user_address):
    user_state = get_user_state(vault_contract, user_address)
    pps = get_pps(vault_contract)
    pending_withdrawal = get_pending_withdrawal_shares(vault_contract, user_address)
    total_balance = (user_state[1] * pps) / 1e12

    init_deposit = user_state[0] / 1e6
    total_shares = user_state[1] / 1e6
    pending_withdrawal = pending_withdrawal / 1e6

    return init_deposit, total_shares, total_balance, pending_withdrawal


def update_or_create_user_portfolio(
    vault: Vault, deposit: OnchainTransactionHistory, vault_contract
):
    user_portfolio = session.exec(
        select(UserPortfolio).where(
            (func.lower(UserPortfolio.user_address) == func.lower(deposit.from_address))
            & (UserPortfolio.vault_id == vault.id)
            & (UserPortfolio.status == PositionStatus.ACTIVE)
        )
    ).first()

    init_deposit, total_shares, total_balance, pending_withdrawal = (
        get_user_portfolio_data(vault_contract, deposit.from_address)
    )

    if user_portfolio is None:
        user_portfolio = UserPortfolio(
            vault_id=vault.id,
            user_address=deposit.from_address,
            init_deposit=init_deposit,
            total_shares=total_shares,
            total_balance=total_balance,
            pending_withdrawal=pending_withdrawal,
            trade_start_date=datetime.fromtimestamp(deposit.timestamp),
            status=PositionStatus.ACTIVE,
        )
    else:
        user_portfolio.init_deposit = init_deposit
        user_portfolio.total_shares = total_shares
        user_portfolio.total_balance = total_balance
        user_portfolio.pending_withdrawal = pending_withdrawal

    session.add(user_portfolio)
    session.commit()


def fix_incorrect_user_portfolio():
    vault_contract_service = VaultContractService()
    subquery = select(UserPortfolio).where(
        UserPortfolio.status == PositionStatus.ACTIVE,
        UserPortfolio.vault_id != "1679bfd4-48eb-4b77-bf27-c2dae0712f91",
    )

    user_portfolio = session.exec(subquery).all()

    logger.info("Starting to process fix_incorrect_user_portfolio...")
    for user in user_portfolio:
        try:
            vault = session.exec(
                select(Vault).where(Vault.is_active).where(Vault.id == user.vault_id)
            ).first()

            # Check if vault is None and log an error if it is
            if vault is None:
                logger.error(
                    "Vault not found for user %s with vault_id %s",
                    user.user_address,
                    user.vault_id,
                )
                continue  # Skip to the next user if vault is not found

            abi_name = vault_contract_service.get_vault_abi(vault=vault)
            if abi_name != "RockOnyxDeltaNeutralVault":
                continue
            vault_contract, _ = get_vault_contract(vault, abi_name)
            init_deposit, total_shares, total_balance, pending_withdrawal = (
                get_user_portfolio_data(vault_contract, user.user_address)
            )

            user.init_deposit = init_deposit
            user.total_shares = total_shares
            user.total_balance = total_balance
            user.pending_withdrawal = pending_withdrawal

            session.add(user)
        except Exception as e:
            logger.error(
                "Error processing fix_incorrect_user_portfolio_function for address %s: %s",
                user.user_address,
                str(e),
                exc_info=True,
            )

    session.commit()


def fix_user_position_from_onchain():
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

    deposits_query = get_recent_deposits_query(subquery)
    deposits = session.exec(deposits_query).all()

    logger.info("Starting to process fix_user_position_from_onchain...")

    for deposit in deposits:
        try:
            vault = fetch_vault(deposit, vault_contract_service)

            abi_name = vault_contract_service.get_vault_abi(vault=vault)
            if (
                abi_name != "RockOnyxDeltaNeutralVault"
                or vault.id != "1679bfd4-48eb-4b77-bf27-c2dae0712f91"
            ):
                continue

            vault_contract, _ = get_vault_contract(vault, abi_name)

            update_or_create_user_portfolio(
                vault,
                deposit,
                vault_contract,
            )
            logger.info(
                "Successfully processed fix_user_position_from_onchain for address: %s",
                deposit.from_address,
            )

        except Exception as e:
            logger.error(
                "Error processing fix_user_position_from_onchain for address %s: %s",
                deposit.from_address,
                str(e),
                exc_info=True,
            )

    logger.info("Finished processing all fix_user_position_from_onchain.")


if __name__ == "__main__":
    setup_logging_to_console()
    fix_user_position_from_onchain()
    fix_incorrect_user_portfolio()
