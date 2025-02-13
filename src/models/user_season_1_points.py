from sqlmodel import SQLModel, Field
from uuid import UUID, uuid4
from datetime import datetime, timezone

class UserSeason1Points(SQLModel, table=True):
    __tablename__ = "user_season_1_points"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(default=None, foreign_key="users.user_id")
    points: float
    recorded_at: datetime = Field(default=datetime.now(timezone.utc))