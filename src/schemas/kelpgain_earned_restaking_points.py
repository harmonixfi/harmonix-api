from pydantic import BaseModel


class KelpGainEarnedRestakingPoints(BaseModel):
    wallet_address: str | None = None
    total_points: float
    eigen_layer_points: float | None = None
    scroll_points: float | None = None
    karak_points: float | None = None
    linea_points: float | None = None
