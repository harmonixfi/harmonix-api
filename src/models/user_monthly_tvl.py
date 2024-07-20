from sqlmodel import SQLModel, Field
from datetime import datetime, timezone
from uuid import UUID, uuid4

class UserMonthlyTVL(SQLModel, table=True):
    __tablename__ = "user_monthly_tvl"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(nullable=False)
    month: datetime = Field(nullable=False, index=True)
    total_value_locked: float = Field(nullable=False)
    created_at: datetime = Field(default=datetime.now(timezone.utc))
