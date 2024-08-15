from sqlmodel import SQLModel, Field, Session, select
from typing import Any, Optional, Dict
from datetime import datetime


# Define a new SQLModel for storing the vault state
class UserHoldingJobState(SQLModel, table=True):
    __tablename__ = "user_holding_job_state"

    id: Optional[int] = Field(default=None, primary_key=True)
    vault_address: str
    user_positions: str
    cumulative_deployment_fund: float
    latest_block: int
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)
