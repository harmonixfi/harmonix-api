from datetime import datetime
import uuid

import sqlmodel
from sqlalchemy.dialects.postgresql import JSON


class VaultPerformanceBase(sqlmodel.SQLModel):
    datetime: datetime
    total_locked_value: float
    apy_1m: float
    apy_1w: float
    apy_ytd: float | None = None
    benchmark: float
    pct_benchmark: float
    risk_factor: float | None = None
    all_time_high_per_share: float | None = None
    total_shares: float | None = None
    sortino_ratio: float | None = None
    downside_risk: float | None = None
    earned_fee: float | None = None
    unique_depositors: int | None = None
    fee_structure: str | None = None
    projected_apy: float | None = None
    base_weekly_apy: float | None = None
    base_monthly_apy: float | None = None
    reward_weekly_apy: float | None = None
    reward_monthly_apy: float | None = None


class VaultPerformance(VaultPerformanceBase, table=True):
    __tablename__ = "vault_performance"

    id: uuid.UUID = sqlmodel.Field(default_factory=uuid.uuid4, primary_key=True)
    vault_id: uuid.UUID = sqlmodel.Field(foreign_key="vaults.id")
