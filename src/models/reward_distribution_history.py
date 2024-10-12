import uuid
from sqlmodel import SQLModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone


class RewardDistributionHistory(SQLModel, table=True):
    __tablename__ = "reward_distribution_history"

    id: Optional[UUID] = Field(default_factory=uuid.uuid4, primary_key=True)
    vault_id: UUID = Field(foreign_key="vaults.id")
    partner_name: str = Field(index=True)
    total_reward: float
    created_at: datetime = Field(default=datetime.now(timezone.utc), index=True)
