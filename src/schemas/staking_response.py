from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional


class StakingValidatorResponse(BaseModel):
    id: UUID
    slug_name: str


class StakingInfoResponse(BaseModel):
    validator_id: UUID
    wallet_address: str
    total_staked: Optional[float] = None
    total_unstaked: Optional[float] = None
    created_at: datetime
    updated_at: datetime
