from sqlmodel import SQLModel, Field
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Optional

class WTVLHistory(SQLModel, table=True):
    __tablename__ = "wtvl_history"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    session_id: UUID = Field(default=None, foreign_key="reward_sessions.session_id")
    wtvl: float
    recorded_at: datetime = Field(default=datetime.now(timezone.utc))