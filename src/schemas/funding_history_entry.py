from datetime import datetime
from pydantic import BaseModel


class FundingHistoryEntry(BaseModel):
    datetime: datetime
    funding_rate: float
