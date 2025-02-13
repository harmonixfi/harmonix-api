from sqlmodel import SQLModel, Field
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Optional

class TierConfig(SQLModel, table=True):
    __tablename__ = "tier_config"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tier_name: str
    points_required: float
    reward: str
    min_held_days: int
    is_active: bool
    created_at: datetime = Field(default=datetime.now(timezone.utc))

class UserTier(SQLModel, table=True):
    __tablename__ = "user_tier"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_address: str = Field(default=None, foreign_key="users.wallet_address")
    tier_id: UUID = Field(default=None, foreign_key="tier_config.id")
    achieved_at: datetime = Field(default=datetime.now(timezone.utc))