from typing import Optional
from sqlmodel import SQLModel, Field
from uuid import UUID, uuid4
from datetime import datetime, timezone


class UserRewards(SQLModel, table=True):
    __tablename__ = "user_rewards"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    vault_id: UUID = Field(foreign_key="vaults.id")
    wallet_address: str = Field(index=True)
    total_reward: float
    claimed: float = 0
    partner_name: str = Field(index=True)
    created_at: datetime = Field(default=datetime.now(timezone.utc), index=True)
    updated_at: datetime = Field(default=datetime.now(timezone.utc), index=True)
    session_id: Optional[UUID] = Field(foreign_key="reward_sessions.session_id")


class UserRewardAudit(SQLModel, table=True):
    __tablename__ = "user_reward_audit"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_points_id: UUID = Field(foreign_key="user_rewards.id")
    old_value: float
    new_value: float
    created_at: datetime = Field(default=datetime.now(timezone.utc))
