from datetime import datetime
import uuid
from pydantic import BaseModel


class VaultPerformanceBase(BaseModel):
    datetime: datetime
    total_locked_value: float
    apy_1m: float
    apy_1w: float
    apy_ytd: float
    benchmark: float
    pct_benchmark: float
    base_weekly_apy: float | None = None
    base_monthly_apy: float | None = None
    reward_weekly_apy: float | None = None
    reward_monthly_apy: float | None = None


# Properties shared by models stored in DB
class VaultPerformanceInDBBase(VaultPerformanceBase):
    id: uuid.UUID
    vault_id: uuid.UUID

    class Config:
        orm_mode = True


# Properties to return to client
class VaultPerformance(VaultPerformanceInDBBase):
    pass


# Properties properties stored in DB
class VaultPerformanceInDB(VaultPerformanceInDBBase):
    pass
