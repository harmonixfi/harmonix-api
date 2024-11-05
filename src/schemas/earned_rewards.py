from datetime import datetime
from pydantic import BaseModel


class EarnedRewards(BaseModel):
    name: str
    rewards: float
    created_at: datetime | None = None
