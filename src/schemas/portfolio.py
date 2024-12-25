import uuid
from pydantic import BaseModel
from datetime import datetime
from typing import List, Dict, Any

from schemas.earned_rewards import EarnedRewards
from .earned_point import EarnedPoints


class Position(BaseModel):
    id: int
    vault_id: uuid.UUID
    vault_name: str
    vault_address: str
    user_address: str
    total_balance: float
    init_deposit: float
    pnl: float | None = None
    status: str
    trade_start_date: str | None = None
    pending_withdrawal: float | None = None
    pending_deposit: float | None = None
    entry_price: float | None = None
    vault_currency: str | None = None
    current_round: int | None = None
    next_close_round_date: str | None = None
    monthly_apy: float | None = None
    weekly_apy: float | None = None
    slug: str | None = None
    apy: str | None = None
    vault_network: str | None = None
    initiated_withdrawal_at: str | None = None
    points: List[EarnedPoints] = []
    rewards: List[EarnedRewards] = []


class PortfolioBase(BaseModel):
    total_balance: float
    pnl: float
    positions: List[Position] | None = None


class PortfolioInDBBase(PortfolioBase):
    model_config: Dict[str, Any] = {}


class Portfolio(PortfolioBase):
    pass


class PortfolioInDB(PortfolioInDBBase):
    pass


class PortfolioPoint(BaseModel):
    points: List[EarnedPoints] = []
