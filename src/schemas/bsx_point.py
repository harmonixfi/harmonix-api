from datetime import datetime
from pydantic import BaseModel


class BSXPoint(BaseModel):
    start_at: str
    end_at: str
    point: float
    degen_point: float
    status: str
    claim_deadline: datetime
    claimed_at: datetime | None
    claimable: bool
