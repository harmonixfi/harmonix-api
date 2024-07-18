from typing import Optional
from sqlmodel import SQLModel, Field
from uuid import UUID, uuid4
from datetime import datetime, timezone


class ReferralPointsHistory(SQLModel, table=True):
    __tablename__ = "referral_points_history"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    referral_points_id: UUID = Field(foreign_key="referral_points.id")
    point: float
    created_at: datetime = Field(default=datetime.now(timezone.utc))
