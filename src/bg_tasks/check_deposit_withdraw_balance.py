import logging
from datetime import datetime, timedelta, timezone
from typing import List, Tuple
from more_itertools import tabulate
import pandas as pd
from sqlalchemy import func
from sqlmodel import Session, select
from web3 import Web3
from core import constants
from log import setup_logging_to_console, setup_logging_to_file
from models.campaigns import Campaign
from models.onchain_transaction_history import OnchainTransactionHistory
from models.referralcodes import ReferralCode
from models.referrals import Referral
from models.reward_thresholds import RewardThresholds
from models.rewards import Reward
from models.user import User
from models.user_last_30_days_tvl import UserLast30DaysTVL
from models.user_portfolio import UserPortfolio
from core.db import engine
from models.vaults import Vault
from services.vault_contract_service import VaultContractService
from utils.extension_utils import to_amount_pendle, to_tx_aumount
from utils.web3_utils import get_current_pps_by_block


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

session = Session(engine)


def calculate_withdrawals(
    withdrawals: List[OnchainTransactionHistory],
) -> Tuple[float, float]:
    service = VaultContractService()
    total_withdrawal_value = 0
    total_shares = 0

    for withdrawal in withdrawals:
        vault_addresses = service.get_vault_address_by_contract(
            withdrawal.to_address.lower()
        )
        vault = session.exec(
            select(Vault).where(
                func.lower(withdrawal.to_address).in_(
                    func.lower(addr) for addr in vault_addresses
                )
            )
        ).first()

        if not vault:
            continue  # Skip if vault is not found

        if vault.strategy_name == constants.PENDLE_HEDGING_STRATEGY:
            withdrawal_amount = to_amount_pendle(
                withdrawal.input, withdrawal.block_number, vault.network_chain
            )
            shares = withdrawal_amount
        else:
            abi = service.get_vault_abi(vault=vault)
            shares = to_tx_aumount(withdrawal.input)
            vault_contract, _ = service.get_vault_contract(
                vault.network_chain,
                Web3.to_checksum_address(withdrawal.to_address),
                abi,
            )
            pps = get_current_pps_by_block(vault_contract, withdrawal.block_number)
            withdrawal_amount = shares * pps

        total_withdrawal_value += withdrawal_amount
        total_shares += shares

    return total_shares, total_withdrawal_value


def handler(address: str) -> Tuple[str, float, float, float]:
    service = VaultContractService()
    today_timestamp = int(
        datetime(2024, 11, 2, 0, 0, 0, tzinfo=timezone.utc).timestamp()
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
        .where(func.lower(OnchainTransactionHistory.from_address) == address.lower())
    )

    deposits = session.exec(deposits_query).all()

    total_deposit_value = 0
    for deposit in deposits:
        vault_address = service.get_vault_address_by_contract(
            deposit.to_address.lower()
        )
        vault = session.exec(
            select(Vault).where(
                func.lower(deposit.to_address).in_(
                    func.lower(addr) for addr in vault_address
                )
            )
        ).first()
        total_deposit = 0
        if vault.strategy_name == constants.PENDLE_HEDGING_STRATEGY:
            total_deposit = to_amount_pendle(
                deposit.input, deposit.block_number, vault.network_chain
            )

            total_deposit_value = total_deposit_value + total_deposit
        else:
            total_deposit = to_tx_aumount(deposit.input)
            total_deposit_value = total_deposit_value + total_deposit

    withdraw_query = (
        select(OnchainTransactionHistory)
        .where(
            OnchainTransactionHistory.method_id.in_(
                [
                    constants.MethodID.COMPPLETE_WITHDRAWAL.value,
                    constants.MethodID.COMPPLETE_WITHDRAWAL2.value,
                ]
            )
        )
        .where(func.lower(OnchainTransactionHistory.from_address) == address.lower())
    )

    withdraw = session.exec(withdraw_query).all()
    _, total_withdrawal_value = calculate_withdrawals(withdraw)

    init_withdraw_query_today = (
        select(OnchainTransactionHistory)
        .where(
            OnchainTransactionHistory.method_id.in_([constants.MethodID.WITHDRAW.value])
        )
        .where(func.lower(OnchainTransactionHistory.from_address) == address.lower())
        .where(OnchainTransactionHistory.timestamp >= today_timestamp)
    )

    init_withdraw_today = session.exec(init_withdraw_query_today).all()

    total_share_today, init_withdraw_vaule_today = calculate_withdrawals(
        init_withdraw_today
    )

    init_withdraw_query = (
        select(OnchainTransactionHistory)
        .where(
            OnchainTransactionHistory.method_id.in_([constants.MethodID.WITHDRAW.value])
        )
        .where(func.lower(OnchainTransactionHistory.from_address) == address.lower())
    )

    init_withdraw = session.exec(init_withdraw_query).all()

    total_share, init_withdraw_vaule = calculate_withdrawals(init_withdraw)
    return (
        address,
        total_deposit_value,
        total_share_today,
        init_withdraw_vaule_today,
        total_share,
        init_withdraw_vaule,
        total_withdrawal_value,
    )


if __name__ == "__main__":
    # Set column headers

    data = [
        "0x0833cC6673d4DE9d81cFE467Ba34803F43F13ECc",
        "0xC2F60688ea1feCEB16603f2a15d1A5f0B4aAf67B",
        "0x0FeF52802365e820722C9D128cc0c0A45a6A765c",
        "0x0d4eef21D898883a6bd1aE518B60fEf7A951ce4D",
        "0x0e19c5bE36a040d7DD9c107253A50374FF10b01d",
        "0x1e2e17a11Aa97c9F3756905de509Abe8cC0e8d71",
        "0x607Dc2e6E0B4A4BA8DBd80AEe01CF773c1567295",
        "0x1765Eb128DBee78350A504239f47Dbcd510FF822",
        "0x18DCA2522A511D7c7FdF30677E50aF2c539f5b4C",
        "0x77aD2B95689Dcf8034985365003e7A008D732519",
        "0x0F8C856907DfAFB96871AbE09a76586311632ef8",
        "0xD415077732524600Dd2C17e39da192356cA967eE",
        "0x770fbEC8AD2A23eDf8D6df75DDf272FBd1e880A0",
    ]
    print(
        f"{'Wallet':<20} {'Total deposit':<15} {'Init withdraw shares today':<20} {'Init withdraw amount today':<20} {'Init withdraw shares':<20} {'Init withdraw amount':<20}{'Complete withdraw amount':<25}"
    )

    columns = [
        "Wallet",
        "Total deposit",
        "Init withdraw shares today",
        "Init withdraw amount today",
        "Init withdraw shares",
        "Init withdraw amount",
        "Complete withdraw amount",
    ]

    # Fetching data
    data_list = []
    for addrss in data:
        (
            address,
            total_deposit,
            init_withdraw_shares_today,
            init_withdraw_amount_today,
            init_withdraw_shares,
            init_withdraw_amount,
            complete_withdraw_amount,
        ) = handler(addrss)
        data_list.append(
            [
                address,
                total_deposit,
                init_withdraw_shares_today,
                init_withdraw_amount_today,
                init_withdraw_shares,
                init_withdraw_amount,
                complete_withdraw_amount,
            ]
        )

    # Creating DataFrame
    df = pd.DataFrame(data_list, columns=columns)
    # Writing to CSV
    df.to_csv("./output/check_deposit_withdraw_balance.csv", index=False)
