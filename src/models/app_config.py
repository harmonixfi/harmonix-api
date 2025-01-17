from sqlmodel import SQLModel, Field
from datetime import datetime, timezone
from uuid import UUID, uuid4


class AppConfig(SQLModel, table=True):
    __tablename__ = "app_config"
    __table_args__ = {"schema": "config"}
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(nullable=False)
    key: str = Field(nullable=False)
