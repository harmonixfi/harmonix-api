from sqlmodel import SQLModel, Field
from datetime import datetime, timezone
from uuid import UUID, uuid4


class UserAgreement(SQLModel, table=True):
    __tablename__ = "user_agreement"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    wallet_address: str = Field(nullable=False)
    message: str = Field(nullable=False)
    signature: str = Field(nullable=False)
    type: str = Field(nullable=False)
    created_at: datetime = Field(default=datetime.now(timezone.utc))
