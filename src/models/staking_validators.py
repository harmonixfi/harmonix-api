from sqlmodel import SQLModel, Field
from datetime import datetime, timezone
from uuid import UUID, uuid4


class StakingValidator(SQLModel, table=True):
    __tablename__ = "staking_validators"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    slug: str = Field(nullable=False)
    hype_validator_id: str = Field(nullable=False)
