import uuid
from sqlmodel import Field, SQLModel


class OnchainTransactionHistory(SQLModel, table=True):
    __tablename__ = "onchain_transaction_history"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tx_hash: str = Field(index=True)
    block_number: int = Field(index=True)
    from_address: str
    to_address: str
    method_id: str
    input: str
    data: str
    value: float
