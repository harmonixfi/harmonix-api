import uuid
from pydantic import BaseModel
from typing import List, Dict, Any

class WithdrawQuoteResponse(BaseModel):
    estimated_withdraw_amount: float
    total_fees: float
    trading_fee: float
    max_slippage: float
    spot_perp_spread: float
    performance_fee: float
    management_fee: float