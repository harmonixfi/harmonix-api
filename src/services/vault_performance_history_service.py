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
        if vault_performances:
            total_value = float(vault_performances[-1].total_locked_value)  
            has_data = True
        else:
            total_value = 0.0
            has_data = False
        
        return total_value, has_data

    def process_vault_performance(self, vault, date: datetime) -> float:
        if vault.update_frequency == constants.UpdateFrequency.weekly.value and date.weekday() == 4:
            current_tvl, has_data  = self.get_tvl(vault.id, date)       
            previous_tvl,_ = self.get_tvl(vault.id, date - timedelta(days=7))
            if has_data is False:
                current_tvl = previous_tvl
        else:
            current_tvl,has_data = self.get_tvl(vault.id, date)
            previous_tvl,_ = self.get_tvl(vault.id, date - timedelta(days=1))
            if has_data is False:
                current_tvl = previous_tvl

        tvl_change = current_tvl - previous_tvl
        total_deposit = self.calculate_total_deposit(date, vault=vault)

        return tvl_change - total_deposit

    def insert_vault_performance_history(
        self, yield_data: float, vault_id: uuid.UUID, date: datetime
    ):
        vault_performance_history = VaultPerformanceHistory(
            datetime=date, total_locked_value=yield_data, vault_id=vault_id
        )
        self.session.add(vault_performance_history)
        self.session.commit()

    def calculate_total_deposit(self, vault_performance_date: datetime, vault: Vault):
        """Calculate the total deposits for a specific date."""
        end_date = int(vault_performance_date.timestamp())
        start_date = int((vault_performance_date - timedelta(hours=24)).timestamp())

        deposits_query = (
            select(OnchainTransactionHistory)
            .where(
                OnchainTransactionHistory.method_id == constants.MethodID.DEPOSIT.value
            )
            .where(
                OnchainTransactionHistory.to_address == vault.contract_address.lower()
            )
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
