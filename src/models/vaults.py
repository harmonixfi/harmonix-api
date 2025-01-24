from datetime import datetime
import enum
from typing import List, Optional
import uuid

import sqlmodel


# create vault categry enum: Yield, Restaking
class VaultCategory(str, enum.Enum):
    real_yield = "real_yield"
    points = "points"
    rewards = "rewards"
    real_yield_v2 = "real_yield_v2"


# create network enum: Ethereum, BSC, ArbitrumOne, Base, Blast
class NetworkChain(str, enum.Enum):
    ethereum = "ethereum"
    bsc = "bsc"
    arbitrum_one = "arbitrum_one"
    base = "base"
    blast = "blast"
    sepolia = "sepolia"


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
    base_weekly_apy: float | None = None
    base_monthly_apy: float | None = None
    reward_weekly_apy: float | None = None
    reward_monthly_apy: float | None = None
    apy_15d: float | None = None
    apy_45d: float | None = None
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
    maturity_date: str | None = None
    pendle_market_address: str | None = None
    underlying_asset: str | None = None
    order: int | None = None
    tags: str | None = None

    # Method to serialize list of tags to string
    def set_tags(self, tags_list: List[str]):
        self.tags = ",".join(tags_list)

    # Method to deserialize string to list of tags
    def get_tags(self) -> List[str]:
        if self.tags:
            return self.tags.split(",")
        return []


# Metadata table for storing leverage information
class VaultMetadata(sqlmodel.SQLModel, table=True):
    __tablename__ = "vault_metadata"

    id: uuid.UUID = sqlmodel.Field(default_factory=uuid.uuid4, primary_key=True)
    vault_id: uuid.UUID = sqlmodel.Field(foreign_key="vaults.id")
    leverage: float | None = None
    borrow_apr: float | None = None
    health_factor: float | None = None
    open_position_size: float | None = None
    goldlink_trading_account: str | None
    last_updated: datetime = sqlmodel.Field(default_factory=datetime.utcnow)

    deposit_token: Optional[str] | None = None
    # Relationship to the Vault
    vault: "Vault" = sqlmodel.Relationship(back_populates="vault_metadata")


# Database model, database table inferred from class name
class Vault(VaultBase, table=True):
    __tablename__ = "vaults"

    group_id: uuid.UUID | None = sqlmodel.Field(
        default=None, foreign_key="vault_groups.id"
    )
    vault_group: VaultGroup | None = sqlmodel.Relationship(back_populates="vaults")
    update_frequency: str | None = sqlmodel.Field(default="daily")
    pt_address: str | None = None
    ui_category: Optional[str] | None = None

    # Relationship to VaultMetadata
    vault_metadata: List[VaultMetadata] = sqlmodel.Relationship(back_populates="vault")
