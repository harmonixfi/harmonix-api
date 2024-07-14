from typing import List, Optional
import uuid
from pydantic import BaseModel, ConfigDict
from datetime import datetime

from models.point_distribution_history import PointDistributionHistory
from models.vaults import NetworkChain, VaultCategory

from .earned_point import EarnedPoints


class VaultBase(BaseModel):
    id: uuid.UUID
    name: str
    # apr: float | None = None
    contract_address: str | None = None
    # monthly_apy: float | None = None
    # weekly_apy: float | None = None
    max_drawdown: float | None = None
    # vault_capacity: int | None = None
    # vault_currency: str | None = None
    current_round: int | None = None
    next_close_round_date: datetime | None = None
    slug: str | None = None
    category: VaultCategory | None = None
    network_chain: NetworkChain | None = None
    strategy_name: str | None = None
    points: List[EarnedPoints] = []


# Properties shared by models stored in DB
class VaultInDBBase(VaultBase):
    model_config = ConfigDict(from_attributes=True)


# Properties to return to client
class Vault(VaultInDBBase):
    apy: float | None = None
    tvl: float | None = None
    is_default: bool | None = None

    supported_network: list[NetworkChain] | None = None


# Properties properties stored in DB
class VaultInDB(VaultInDBBase):
    pass


class GroupSchema(BaseModel):
    id: uuid.UUID
    name: str
    tvl: float | None = None
    apy: float | None = None
    vaults: List[Vault] = []
    points: List[EarnedPoints] = []

    class Config:
        orm_mode = True