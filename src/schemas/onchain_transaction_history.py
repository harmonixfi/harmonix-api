from typing import Optional
import uuid
from pydantic import BaseModel
from datetime import datetime, time


class OnchainTransactionHistory(BaseModel):
    id: uuid.UUID
    tx_hash: str
    timestamp: int
    datetime: datetime
    method_id: str
    input: str
    amount: float = 0.0
    age: time
    vault_address: Optional[str] = None
