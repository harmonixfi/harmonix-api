import uuid
from sqlmodel import Field, SQLModel


class OnchainTransactionHistory(SQLModel, table=True):
    __tablename__ = "onchain_transaction_history"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tx_hash: str = Field(index=True, unique=True)
    block_number: int = Field(index=True)
    timestamp: int = Field(index=True, nullable=True)
    from_address: str = Field(index=True)
    to_address: str
    method_id: str = Field(index=True)
    input: str
    value: float
    chain: str = Field(default="arbitrum_one", index=True, nullable=True)
