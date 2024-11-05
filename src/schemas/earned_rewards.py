from datetime import datetime
from pydantic import BaseModel


class EarnedRewards(BaseModel):
    name: str
    arb_rewards: float
    created_at: datetime | None = None
