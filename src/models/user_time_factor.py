from sqlmodel import SQLModel, Field
from uuid import UUID, uuid4
from datetime import datetime, timezone


class UserTimeFactor(SQLModel, table=True):
    __tablename__ = "user_time_factor"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_portfolio_id: int = Field(default=None, foreign_key="user_portfolio.id")
    time_factor: float
    calculated_at: datetime = Field(default=datetime.now(timezone.utc))
