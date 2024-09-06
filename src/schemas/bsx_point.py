from datetime import datetime
from pydantic import BaseModel


class BSXPoint(BaseModel):
    start_at: datetime
    end_at: datetime
    point: float
    degen_point: float
    status: str
    claim_deadline: datetime
    claimed_at: datetime | None
    claimable: bool
