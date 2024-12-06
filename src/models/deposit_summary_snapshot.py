from sqlmodel import SQLModel, Field
from uuid import UUID, uuid4
from datetime import datetime as dt, timezone

import sqlmodel


class DepositSummarySnapshot(SQLModel, table=True):
    __tablename__ = "deposit_summary_snapshot"
    __table_args__ = {"schema": "reports"}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    datetime: dt = sqlmodel.Field(default=dt.now(timezone.utc), index=True)
    deposit_7_day: float
    deposit_30_day: float
