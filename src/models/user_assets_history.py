from sqlmodel import SQLModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


class UserHistory(SQLModel, table=True):
    __tablename__ = "user_history"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_address: str
    total_shares: float
    vault_total_shares: float
    asset_amount: float
    asset_address: str
    asset_symbol: str
    asset_decimals: int
    holding_percentage: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    block_number: int
