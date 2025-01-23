from datetime import datetime, timedelta, timezone
import json
from typing import List, Optional
import uuid

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, bindparam, desc, func, text
from sqlmodel import Session, and_, select, or_

from api.api_v1.endpoints.vaults import (
    _get_last_price_per_share,
    _update_vault_apy,
    get_earned_points,
    get_earned_rewards,
)
import schemas
from api.api_v1.deps import SessionDep
from models import Vault
from models.vaults import NetworkChain, VaultCategory, VaultGroup, VaultMetadata
from schemas.vault import GroupSchema, SupportedNetwork, VaultExtended, VaultSortField

router = APIRouter()


@router.get("/vaults/", response_model=List[schemas.VaultExtended])
async def get_all_vaults(
    session: SessionDep,
    category: Optional[str] = Query(None),
    network_chain: NetworkChain = Query(None),
    tags: Optional[str] = Query(None),
    deposit_token: Optional[str] = Query(None),
    sort_by: Optional[List[VaultSortField]] = Query(
        default=None,
        description="Optional sort fields. Example: sort_by=category&sort_by=apy_desc",
    ),
):
    statement = select(Vault).where(Vault.is_active == True)
    conditions = []
    if category:
        conditions.append(Vault.ui_category == category)

    if network_chain:
        conditions.append(Vault.network_chain == network_chain)

    if tags:
        conditions.append(Vault.tags.contains(tags))

    # Add deposit token filter
    # Add deposit token filter using regex pattern for exact match
    if deposit_token:
        statement = statement.join(Vault.vault_metadata)
        # Match exact token in comma-separated list
        pattern = (
            f"(^{deposit_token}$|^{deposit_token},|,{deposit_token}$|,{deposit_token},)"
        )
        conditions.append(VaultMetadata.deposit_token.regexp_match(pattern))

    if conditions:
        statement = statement.where(and_(*conditions))

    vaults = session.exec(statement).all()
    results = []

    for vault in vaults:
        schema_vault = _update_vault_apy(vault, session=session)
        schema_vault.points = get_earned_points(session, vault)
        schema_vault.rewards = get_earned_rewards(session, vault)

        schema_vault.price_per_share = _get_last_price_per_share(
            session=session, vault_id=vault.id
        )

        for vault_metata in vault.vault_metadata:
            result = schemas.VaultExtended.model_validate(schema_vault)
            result.deposit_token = (
                vault_metata.deposit_token.split(",")
                if vault_metata.deposit_token
                else ["USDC"]
            )
            result.ui_category = vault.ui_category
            results.append(result)

    # Apply sorting only if sort_by is provided
    if sort_by:
        for sort_field in reversed(sort_by):
            if sort_field == VaultSortField.TVL_DESC:
                results.sort(key=lambda x: float(x.tvl or 0), reverse=True)
            elif sort_field == VaultSortField.TVL_ASC:
                results.sort(key=lambda x: float(x.tvl or 0))
            elif sort_field == VaultSortField.NAME_ASC:
                results.sort(key=lambda x: x.name.lower())
            elif sort_field == VaultSortField.NAME_DESC:
                results.sort(key=lambda x: x.name.lower(), reverse=True)
            elif sort_field == VaultSortField.APY_DESC:
                results.sort(key=lambda x: float(x.apy or 0), reverse=True)
            elif sort_field == VaultSortField.APY_ASC:
                results.sort(key=lambda x: float(x.apy or 0))
            elif sort_field == VaultSortField.CATEGORY:
                results.sort(key=lambda x: str(x.category))
            elif sort_field == VaultSortField.ORDER:
                results.sort(key=lambda x: x.order)

    return results
