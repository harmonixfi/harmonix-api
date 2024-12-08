from sqlmodel import SQLModel, Field
from uuid import UUID, uuid4
from datetime import datetime as dt, timezone

import sqlmodel


class APYRateHistory(SQLModel, table=True):
    __tablename__ = "apy_rate_history"
    __table_args__ = {"schema": "reports"}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    datetime: dt = sqlmodel.Field(default=dt.now(timezone.utc), index=True)
    apy_rate: float
    partner_name: str = Field(index=True)
