from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime, timezone
from uuid import UUID, uuid4


class UserStaking(SQLModel, table=True):
    __tablename__ = "user_stakings"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    validator_id: UUID
    wallet_address: str
    total_staked: Optional[float] | None = None
    total_unstaked: Optional[float] | None = None
    created_at: datetime = Field(default=datetime.now(timezone.utc), index=True)
    updated_at: datetime = Field(default=datetime.now(timezone.utc), index=True)
