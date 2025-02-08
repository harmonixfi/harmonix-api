from sqlmodel import SQLModel, Field
from datetime import datetime, timezone
from uuid import UUID, uuid4


class StakingValidator(SQLModel, table=True):
    __tablename__ = "staking_validators"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    slug_name: str = Field(nullable=False)
