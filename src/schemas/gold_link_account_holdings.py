from pydantic import BaseModel


class GoldLinkAccountHoldings(BaseModel):
    collateral: float
    loan: float
    interest_index_last: float
