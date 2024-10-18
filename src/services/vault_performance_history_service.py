from typing import List, Tuple
from sqlalchemy import func
from sqlmodel import Session, select
from datetime import datetime, timedelta
import uuid
import pytz
from telegram import Contact
from web3 import Web3

from core import constants
from models.onchain_transaction_history import OnchainTransactionHistory
from models.vault_performance import VaultPerformance
from models.vault_performance_history import VaultPerformanceHistory
from models.vaults import Vault
from utils.extension_utils import (
    to_amount_pendle,
    to_tx_aumount,
)
from utils.web3_utils import get_current_pps_by_block
from core.abi_reader import read_abi


class VaultPerformanceHistoryService:
    def __init__(self, session: Session):
        self.session = session

    def get_active_vaults(self) -> List[Vault]:
        result = self.session.exec(select(Vault).where(Vault.is_active)).all()
        return result

    def get_vault_performances(self, vault_id: uuid.UUID, date: datetime):
        date_query = date.date()
        return self.session.exec(
            select(VaultPerformance)
            .where(VaultPerformance.vault_id == vault_id)
            .where(func.date(VaultPerformance.datetime) == date_query)
            .order_by(VaultPerformance.datetime.asc())
        ).all()

    def get_tvl(self, vault: Vault, date: datetime) -> Tuple[float, bool]:
        vault_performances = self.get_vault_performances(vault.id, date)

        end_date = date
        start_date = end_date - timedelta(days=1)
        if vault_performances:
            total_value = float(vault_performances[0].total_locked_value)
            end_date = vault_performances[0].datetime
            if vault.update_frequency == constants.UpdateFrequency.weekly.value:
                start_date = end_date - timedelta(days=7)
            else:
                start_date = end_date - timedelta(days=1)
        else:
            total_value = 0.0

        return total_value, start_date, end_date

    def process_vault_performance(self, vault, date: datetime) -> float:
        utc_tz = pytz.utc
        end_date = date
        start_date = end_date - timedelta(days=1)
        if (
            vault.update_frequency == constants.UpdateFrequency.weekly.value
            and date.weekday() == 4
        ):
            current_tvl, start_date, end_date = self.get_tvl(vault, date)
            previous_tvl, _, _ = self.get_tvl(vault, date - timedelta(days=7))
        else:
            current_tvl, start_date, end_date = self.get_tvl(vault, date)
            previous_tvl, _, _ = self.get_tvl(vault, date - timedelta(days=1))

        tvl_change = current_tvl - previous_tvl
        start_date = start_date.replace(second=0)
        end_date = end_date.replace(second=0)
        total_deposit = self.calculate_total_deposit(start_date, end_date, vault=vault)

        return tvl_change - total_deposit

    def insert_vault_performance_history(
        self, yield_data: float, vault_id: uuid.UUID, date: datetime
    ):
        vault_performance_history = VaultPerformanceHistory(
            datetime=date, total_locked_value=yield_data, vault_id=vault_id
        )
        self.session.add(vault_performance_history)
        self.session.commit()

    def get_vault_address_historical(self, vault: Vault) -> List[str]:
        if (
            vault.contract_address.lower()
            == "0x4a10c31b642866d3a3df2268cecd2c5b14600523".lower()
        ):
            return [
                "0x4a10c31b642866d3a3df2268cecd2c5b14600523",
                "0xF30353335003E71b42a89314AAaeC437E7Bc8F0B",
                "0x2b7cdad36a86fd05ac1680cdc42a0ea16804d80c",
            ]

        if (
            vault.contract_address.lower()
            == "0xd531d9212cB1f9d27F9239345186A6e9712D8876".lower()
        ):
            return [
                "0x50CDDCBa6289d3334f7D40cF5d312E544576F0f9",
                "0x607b19a600F2928FB4049d2c593794fB70aaf9aa",
                "0xC9A079d7d1CF510a6dBa8dA8494745beaE7736E2",
                "0x389b5702FA8bF92759d676036d1a90516C1ce0C4",
                "0xd531d9212cB1f9d27F9239345186A6e9712D8876",
            ]
        if (
            vault.contract_address.lower()
            == "0x316CDbBEd9342A1109D967543F81FA6288eBC47D".lower()
        ):
            return [
                vault.contract_address,
                "0x0bD37D11e3A25B5BB0df366878b5D3f018c1B24c",
                "0x18994527E6FfE7e91F1873eCA53e900CE0D0f276",
                "0x55c4c840F9Ac2e62eFa3f12BaBa1B57A1208B6F5",
            ]
        if (
            vault.contract_address.lower()
            == "0xE46C3BE33D0C682fCA5F965D244398E924000705".lower()
        ):
            return ["0xE46C3BE33D0C682fCA5F965D244398E924000705"]

        # GoldLink
        if (
            vault.contract_address.lower()
            == "0xa9BE190b8348F18466dC84cC2DE69C04673c5aca".lower()
        ):
            return ["0XA9BE190B8348F18466DC84CC2DE69C04673C5ACA"]
        return [vault.contract_address]

    def calculate_total_deposit(
        self,
        vault_performance_start_date: datetime,
        vault_performance_end_date: datetime,
        vault: Vault,
    ):
        """Calculate the total deposits for a specific date."""
        end_date = int(vault_performance_end_date.timestamp())
        start_date = int(vault_performance_start_date.timestamp())

        contract_address = [
            address.lower() for address in self.get_vault_address_historical(vault)
        ]
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
            .where(OnchainTransactionHistory.to_address.in_(contract_address))
            .where(OnchainTransactionHistory.timestamp <= end_date)
            .where(OnchainTransactionHistory.timestamp >= start_date)
        )

        deposits = self.session.exec(deposits_query).all()

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
            .where(OnchainTransactionHistory.to_address.in_(contract_address))
            .where(OnchainTransactionHistory.timestamp <= end_date)
            .where(OnchainTransactionHistory.timestamp >= start_date)
        )

        withdraw = self.session.exec(withdraw_query).all()
        total_deposit = 0
        total_withdraw = 0
        if vault.strategy_name == constants.PENDLE_HEDGING_STRATEGY:
            total_deposit = sum(
                to_amount_pendle(tx.input, tx.block_number, vault.network_chain)
                for tx in deposits
            )
            total_withdraw = sum(
                to_amount_pendle(tx.input, tx.block_number, vault.network_chain)
                for tx in withdraw
            )
        else:
            total_deposit = sum(to_tx_aumount(tx.input) for tx in deposits)

            abi = self.get_vault_abi(vault=vault)

            for tx in withdraw:
                shares = to_tx_aumount(tx.input)
                vault_contract, _ = self.get_vault_contract(
                    vault.network_chain,
                    Web3.to_checksum_address(tx.to_address),
                    abi,
                )
                pps = get_current_pps_by_block(vault_contract, tx.block_number)
                usdc_amount = shares * pps
                total_withdraw = total_withdraw + usdc_amount

        return total_deposit - total_withdraw

    def get_by(
        self, vault_id: str, start_date: datetime, end_date: datetime
    ) -> List[VaultPerformanceHistory]:
        query = (
            select(VaultPerformanceHistory)
            .where(VaultPerformanceHistory.vault_id == vault_id)
            .where(VaultPerformanceHistory.datetime <= end_date)
            .where(VaultPerformanceHistory.datetime >= start_date)
        )

        return self.session.exec(query).all()

    def get_vault_contract(
        self,
        network_chain: str,
        contract_address,
        abi_name: str = "RockOnyxDeltaNeutralVault",
    ) -> tuple[Contact, Web3]:

        w3 = Web3(Web3.HTTPProvider(constants.NETWORK_RPC_URLS[network_chain]))

        rockonyx_delta_neutral_vault_abi = read_abi(abi_name)
        vault_contract = w3.eth.contract(
            address=contract_address,
            abi=rockonyx_delta_neutral_vault_abi,
        )
        return vault_contract, w3

    def get_vault_abi(self, vault):
        abi = "RockOnyxDeltaNeutralVault"

        if vault.slug == constants.SOLV_VAULT_SLUG:
            abi = "solv"
        elif vault.strategy_name == constants.DELTA_NEUTRAL_STRATEGY:
            abi = "RockOnyxDeltaNeutralVault"
        elif vault.strategy_name == constants.OPTIONS_WHEEL_STRATEGY:
            abi = "rockonyxstablecoin"
        elif vault.strategy_name == constants.PENDLE_HEDGING_STRATEGY:
            abi = "pendlehedging"

        return abi
