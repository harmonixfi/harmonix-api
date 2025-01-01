from datetime import datetime
from pydantic import BaseModel


class UserEarnedRewards(BaseModel):
    name: str
    unclaim: float
    claimed: float
    created_at: datetime | None = None
