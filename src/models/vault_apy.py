from datetime import datetime
import enum
from typing import List, Optional
import uuid

import sqlmodel


class VaultAPYComponent(sqlmodel.SQLModel, table=True):
    __tablename__ = "vault_apy_component"

    id: uuid.UUID = sqlmodel.Field(default_factory=uuid.uuid4, primary_key=True)
    vault_apy_id: uuid.UUID = sqlmodel.Field(
        foreign_key="vault_apy.id"
    )  # Foreign key to Vault

    component_name: str | None = None
    component_apy: float = sqlmodel.Field(
        default=0.0
    )  # The overall vault APY with default 0

    vault_apy: "VaultAPY" = sqlmodel.Relationship(back_populates="apy_components")


class VaultAPY(sqlmodel.SQLModel, table=True):
    __tablename__ = "vault_apy"

    id: uuid.UUID = sqlmodel.Field(default_factory=uuid.uuid4, primary_key=True)
    vault_id: uuid.UUID = sqlmodel.Field(
        foreign_key="vaults.id"
    )  # Foreign key to Vault

    total_apy: float = sqlmodel.Field(
        default=0.0
    )  # The overall vault APY with default 0

    apy_components: List[VaultAPYComponent] = sqlmodel.Relationship(
        back_populates="vault_apy"
    )
