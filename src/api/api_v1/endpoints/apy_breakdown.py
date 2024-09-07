from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from sqlmodel import select

from api.api_v1.deps import SessionDep
from models.user_assets_history import UserHoldingAssetHistory
from models.vault_apy_breakdown import VaultAPY
from models.vaults import NetworkChain, Vault
from schemas.user_assets import UserAssetAmount

router = APIRouter()


@router.get("/apy-breakdown/{vault_id}")
def get_apy_breakdown(session: SessionDep, vault_id: str):

    statement = select(Vault).where(Vault.id == vault_id)
    vault = session.exec(statement).first()
    if vault is None:
        raise HTTPException(
            status_code=400,
            detail="The data not found in the database.",
        )

    statement = select(VaultAPY).where(VaultAPY.vault_id == vault_id)
    vault_apy = session.exec(statement).first()
    if vault_apy is None:
        return []
    data = [
        {component.component_name: component.component_apy}
        for component in vault_apy.apy_components
    ]

    return data
