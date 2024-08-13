from datetime import datetime
import uuid
import sqlmodel

class VaultPerformanceHistoryBase(sqlmodel.SQLModel):
    datetime: datetime
    total_locked_value: float
    
class VaultPerformanceHistory(VaultPerformanceHistoryBase, table=True):
    __tablename__ = "vault_performance_history"

    id: uuid.UUID = sqlmodel.Field(default_factory=uuid.uuid4, primary_key=True)
    vault_id: uuid.UUID = sqlmodel.Field(foreign_key="vaults.id")
