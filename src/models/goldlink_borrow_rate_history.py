from sqlmodel import SQLModel, Field
from uuid import UUID, uuid4
from datetime import datetime as dt, timezone

import sqlmodel


class GoldlinkBorrowRateHistory(SQLModel, table=True):
    __tablename__ = "goldlink_borrow_rate_history"
    __table_args__ = {"schema": "reports"}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    datetime: dt = sqlmodel.Field(default=dt.now(timezone.utc), index=True)
    apy_rate: float
