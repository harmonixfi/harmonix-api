from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel
from uuid import UUID


class WhitelistWallet(SQLModel, table=True):
    __tablename__ = "whitelist_wallets"
    __table_args__ = {"schema": "config"}

    id: Optional[UUID] = Field(default=None, primary_key=True)
    vault_slug: str = Field(index=True)
    wallet_address: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
