from datetime import datetime as dt, timezone
import uuid
import sqlmodel


class VaultPerformanceHistoryBase(sqlmodel.SQLModel):
    datetime: dt = sqlmodel.Field(default=dt.now(timezone.utc), index=True)
    total_locked_value: float


class VaultPerformanceHistory(VaultPerformanceHistoryBase, table=True):
    __tablename__ = "vault_performance_history"

    id: uuid.UUID = sqlmodel.Field(default_factory=uuid.uuid4, primary_key=True)
    vault_id: uuid.UUID = sqlmodel.Field(foreign_key="vaults.id")
