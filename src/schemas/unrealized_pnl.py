import uuid
from pydantic import BaseModel
from typing import List, Dict, Any

class UnrealizedPnl(BaseModel):
    trading_fee: float
    max_slippage: float
    negative_funding_fee: float
    projected_record: float | None = None