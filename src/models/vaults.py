from datetime import datetime
import enum
import uuid

import sqlmodel

# create vault categry enum: Yield, Restaking
class VaultCategory(str, enum.Enum):
    real_yield = "real_yield"
    points = "points"


# create network enum: Ethereum, BSC, ArbitrumOne, Base, Blast
class NetworkChain(str, enum.Enum):
    ethereum = "ethereum"
    bsc = "bsc"
    arbitrum_one = "arbitrum_one"
    base = "base"
    blast = "blast"


class VaultGroup(sqlmodel.SQLModel, table=True):
    __tablename__ = "vault_groups"

    id: uuid.UUID = sqlmodel.Field(default_factory=uuid.uuid4, primary_key=True)
    name: str

    default_vault_id: uuid.UUID | None = None
    vaults: list["Vault"] = sqlmodel.Relationship(back_populates="vault_group")


class VaultBase(sqlmodel.SQLModel):
    id: uuid.UUID = sqlmodel.Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    contract_address: str | None = None
    apr: float | None = None
    tvl: float | None = None
    ytd_apy: float | None = None
    monthly_apy: float | None = None
    weekly_apy: float | None = None
    max_drawdown: float | None = None
    vault_capacity: int | None = None
    vault_currency: str | None = None
    current_round: int | None = None
    next_close_round_date: datetime | None = None
    slug: str | None = None
    routes: str | None = None
    category: VaultCategory = sqlmodel.Field(
        default=VaultCategory.real_yield, nullable=True
    )
    network_chain: NetworkChain = sqlmodel.Field(
        default=NetworkChain.arbitrum_one, nullable=True
    )
    strategy_name: str | None = None
    is_active: bool | None = None
    owner_wallet_address: str | None = None
    order: int | None = None


# Database model, database table inferred from class name
class Vault(VaultBase, table=True):
    __tablename__ = "vaults"
    
    group_id: uuid.UUID | None = sqlmodel.Field(default=None, foreign_key="vault_groups.id")
    vault_group: VaultGroup | None = sqlmodel.Relationship(back_populates="vaults")
