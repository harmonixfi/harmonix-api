from pydantic import BaseModel


class EarnedRewards(BaseModel):
    wallet_address: str | None = None
    total_rewards: float
    partner_name: str
    eigen_layer_rewards: float | None = None
