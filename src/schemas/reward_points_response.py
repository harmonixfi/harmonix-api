from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from models.rewards import Reward
from models.user_points import UserPoints

class Rewards(BaseModel):
    reward_percentage: float
    depositors: int
    high_balance_depositors: int

class Points(BaseModel):
    points: float
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    session_name: Optional[str] = None
    partner_name: Optional[str] = None

class ReferralPoints(BaseModel):
    points: float
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
