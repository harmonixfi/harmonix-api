from sqlmodel import SQLModel, Field
from datetime import datetime, timezone
from uuid import UUID, uuid4

class Campaign(SQLModel, table=True):
    __tablename__ = "campaigns"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(nullable=False)
    start_date: datetime = Field(nullable=True)
    end_date: datetime = Field(nullable=True)
    status: str = Field(nullable=False)  # Could be Enum if you have defined statuses
    created_at: datetime = Field(default=datetime.now(timezone.utc))
