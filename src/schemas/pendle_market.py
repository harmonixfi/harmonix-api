from pydantic import BaseModel


class PendleMarket(BaseModel):
    id: str
    chainId: int
    symbol: str
    expiry: str
    underlyingInterestApy: float
    impliedApy: float
    ptDiscount: float
