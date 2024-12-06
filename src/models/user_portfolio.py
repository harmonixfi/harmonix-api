from typing import Optional
from sqlmodel import SQLModel, Field
from enum import Enum
from uuid import UUID
from datetime import datetime, timezone


class PositionStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"


class UserPortfolio(SQLModel, table=True):
    __tablename__ = "user_portfolio"
    id: Optional[int] = Field(default=None, primary_key=True)
    vault_id: UUID
    user_address: str
    total_balance: float
    init_deposit: float
    entry_price: float | None = None
    exit_price: float | None = None
    pnl: float | None = None
    pending_deposit: float | None = Field(default=0, nullable=True)
    pending_withdrawal: float | None = None
    total_shares: float | None = None
    status: PositionStatus = Field(default=PositionStatus.ACTIVE)
    trade_start_date: datetime = Field(default=datetime.now(tz=timezone.utc))
    trade_end_date: datetime | None = None
    initiated_withdrawal_at: datetime = Field(default=None, nullable=True)
