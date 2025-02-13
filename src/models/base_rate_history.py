from sqlmodel import SQLModel, Field
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Optional


class BaseRateHistory(SQLModel, table=True):
    __tablename__ = "base_rate_history"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    session_id: UUID = Field(default=None, foreign_key="reward_sessions.session_id")
    base_rate: float
    point_distributed: float
    calculated_at: datetime = Field(default=datetime.now(timezone.utc))