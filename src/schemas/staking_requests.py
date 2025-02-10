from uuid import UUID
from pydantic import BaseModel


class UpdateTotalStakedRequest(BaseModel):
    validator_id: UUID
    wallet_address: str
    total_staked: float
    signature: str
    message: str


class UpdateTotalUnstakedRequest(BaseModel):
    validator_id: UUID
    wallet_address: str
    total_unstaked: float
    signature: str
    message: str
