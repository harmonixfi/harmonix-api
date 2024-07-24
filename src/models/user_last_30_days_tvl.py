from sqlmodel import SQLModel, Field
from datetime import datetime, timezone
from uuid import UUID, uuid4

class UserLast30DaysTVL(SQLModel, table=True):
    __tablename__ = "user_last_30_days_tvl"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(nullable=False)
    weighted_median_share: float = Field(nullable=False)
    share_deposited: float = Field(nullable=False)
    share_withdraw: float = Field(nullable=False)
    total_value_locked: float = Field(nullable=False)
    created_at: datetime = Field(default=datetime.now(timezone.utc))
