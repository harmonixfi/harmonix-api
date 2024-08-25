from typing import List, Tuple
from sqlalchemy import func
from sqlmodel import Session, select
from datetime import datetime, timedelta
import uuid

from core import constants
from models.onchain_transaction_history import OnchainTransactionHistory
from models.vault_performance import VaultPerformance
from models.vault_performance_history import VaultPerformanceHistory
from models.vaults import Vault
from utils.extension_utils import to_tx_aumount


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

    def get_tvl(self, vault_id: uuid.UUID, date: datetime) -> Tuple[float, bool]:
        vault_performances = self.get_vault_performances(vault_id, date)

        end_date = date
        start_date = end_date - timedelta(days=1)
        if vault_performances:
            total_value = float(vault_performances[0].total_locked_value)
            end_date = vault_performances[0].datetime
            start_date = end_date - timedelta(days=1)
        else:
            total_value = 0.0

        return total_value, start_date, end_date

    def process_vault_performance(self, vault, date: datetime) -> float:

        end_date = date
        start_date = end_date - timedelta(days=1)
        if (
            vault.update_frequency == constants.UpdateFrequency.weekly.value
            and date.weekday() == 4
        ):
            current_tvl, start_date, end_date = self.get_tvl(vault.id, date)
            previous_tvl, _, _ = self.get_tvl(vault.id, date - timedelta(days=7))
        else:
            current_tvl, start_date, end_date = self.get_tvl(vault.id, date)
            previous_tvl, _, _ = self.get_tvl(vault.id, date - timedelta(days=1))

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
            ]

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
                OnchainTransactionHistory.method_id == constants.MethodID.DEPOSIT.value
            )
            .where(OnchainTransactionHistory.to_address.in_(contract_address))
            .where(OnchainTransactionHistory.timestamp <= end_date)
            .where(OnchainTransactionHistory.timestamp >= start_date)
        )

        deposits = self.session.exec(deposits_query).all()

        withdraw_query = (
            select(OnchainTransactionHistory)
            .where(
                OnchainTransactionHistory.method_id
                == constants.MethodID.COMPPLETE_WITHDRAWAL.value
            )
            .where(
                OnchainTransactionHistory.to_address == vault.contract_address.lower()
            )
            .where(OnchainTransactionHistory.timestamp <= end_date)
            .where(OnchainTransactionHistory.timestamp >= start_date)
        )

        withdraw = self.session.exec(withdraw_query).all()

        total_deposit = sum(to_tx_aumount(tx.input) for tx in deposits)
        total_withdraw = sum(to_tx_aumount(tx.input) for tx in withdraw)

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
