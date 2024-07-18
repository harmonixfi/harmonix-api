from sqlmodel import SQLModel, Field
from datetime import datetime, timezone
from uuid import UUID, uuid4
class RewardThresholds(SQLModel, table=True):
    __tablename__ = "reward_thresholds"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tier: int = Field(nullable=False)
    threshold: float = Field(nullable=False)
    commission_rate: float = Field(nullable=False)
    created_at: datetime = Field(default=datetime.now(timezone.utc))
