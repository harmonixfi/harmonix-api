from datetime import datetime as dt, timezone
import uuid
from sqlmodel import SQLModel, Field
from typing import Optional
import sqlmodel


class RewardDistributionConfig(SQLModel, table=True):
    __tablename__ = "reward_distribution_config"
    __table_args__ = {"schema": "config"}
    id: uuid.UUID = sqlmodel.Field(default_factory=uuid.uuid4, primary_key=True)
    vault_id: uuid.UUID = sqlmodel.Field(foreign_key="vaults.id")
    reward_token: str | None = None
    total_reward: float | None = None
    week: int | None = None
    distribution_percentage: float | None = None
    start_date: dt = sqlmodel.Field(default=dt.now(timezone.utc), index=True)
    created_at: dt = sqlmodel.Field(default=dt.now(timezone.utc), index=True)
