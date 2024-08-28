from typing import List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, validator
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
    vault_currency: str | None = None
    current_round: int | None = None
    next_close_round_date: datetime | None = None
    slug: str | None = None
    category: VaultCategory | None = None
    network_chain: NetworkChain | None = None
    maturity_date: NetworkChain | None = None
    strategy_name: str | None = None
    points: List[EarnedPoints] = []


# Properties shared by models stored in DB
class VaultInDBBase(VaultBase):
    model_config = ConfigDict(from_attributes=True)


class SupportedNetwork(BaseModel):
    chain: NetworkChain | None = None
    vault_slug: str | None = None

    def __hash__(self):
        # This creates a hash based on the tuple of all relevant attributes
        return hash((self.chain, self.vault_slug))

    def __eq__(self, other):
        # This ensures equality is based on the same attributes used in the hash
        if isinstance(other, SupportedNetwork):
            return (self.chain, self.vault_slug) == (other.chain, other.vault_slug)
        return False


# Properties to return to client
class Vault(VaultInDBBase):
    apy: float | None = None
    tvl: float | None = None
    is_default: bool | None = None

    supported_networks: List[SupportedNetwork] | None = None
    tags: List[str] | None = None

    @validator("tags", pre=True, always=True)
    def split_str_to_list(cls, v):
        if isinstance(v, str):
            return v.split(",")
        return v


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
