from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime, timezone
from uuid import UUID, uuid4


class UserStakingBalance(SQLModel, table=True):
    __tablename__ = "user_staking_balances"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    validator_id: UUID
    wallet_address: str = Field(index=True)
    total_staked: Optional[float] | None = None
    total_unstaked: Optional[float] | None = None
    created_at: datetime = Field(default=datetime.now(timezone.utc), index=True)
    updated_at: datetime = Field(default=datetime.now(timezone.utc), index=True)
