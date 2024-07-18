from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field
from uuid import UUID, uuid4

class Reward(SQLModel, table=True):
    __tablename__ = "rewards"
    
    reward_id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.user_id")
    referral_code_id: UUID = Field(foreign_key="referral_codes.referral_code_id")
    reward_percentage: float
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    status: str = Field(default="active")  # Could be Enum if you have defined statuses
