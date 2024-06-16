from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from models.rewards import Reward
from models.user_points import UserPoints

class Rewards(BaseModel):
    reward_percentage: float
    depositors: int

class Points(BaseModel):
    points: int
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    session_name: Optional[str] = None