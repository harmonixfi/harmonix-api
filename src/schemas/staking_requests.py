from typing import Optional
from uuid import UUID
from pydantic import BaseModel


class StakingRequest(BaseModel):
    validator_id: UUID
    wallet_address: str
    total_amount: float
    signature: str
    message: str
    tx_hash: Optional[str] | None = None
    chain_id: Optional[str] | None = None
