from pydantic import BaseModel


class UserAssetAmount(BaseModel):
    user_address: str
    asset_amount: float
    asset_amount_in_uint256: int
