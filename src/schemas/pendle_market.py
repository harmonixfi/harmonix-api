from pydantic import BaseModel


class PendleMarket(BaseModel):
    id: str
    chain_id: int
    symbol: str
    expiry: str
    underlying_interest_apy: float
    implied_apy: float
    pt_discount: float
