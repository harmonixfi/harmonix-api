from datetime import datetime, timezone
from sqlmodel import SQLModel, Field
from typing import Optional
from uuid import UUID, uuid4

from core.constants import UserTier


class User(SQLModel, table=True):
    __tablename__ = "users"

    user_id: UUID = Field(default_factory=uuid4, primary_key=True)
    wallet_address: str = Field(index=True, unique=True)
    tier: str = Field(index=True, default=UserTier.DEFAULT.value)
    created_at: datetime = Field(default=datetime.now(timezone.utc))