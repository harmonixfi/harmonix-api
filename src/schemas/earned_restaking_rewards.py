from pydantic import BaseModel


class EarnedRestakingRewards(BaseModel):
    wallet_address: str | None = None
    total_points: float
    partner_name: str
    eigen_layer_points: float | None = None
