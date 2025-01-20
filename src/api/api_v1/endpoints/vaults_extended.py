from datetime import datetime, timedelta, timezone
import json
from typing import List, Optional
import uuid

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, bindparam, desc, func, text
from sqlmodel import Session, and_, select, or_
from web3 import Web3

from models.pps_history import PricePerShareHistory
from models.reward_distribution_config import RewardDistributionConfig
from models.reward_distribution_history import RewardDistributionHistory
from models.user_rewards import UserRewards
from models.vault_apy_breakdown import VaultAPYBreakdown
from models.whitelist_wallets import WhitelistWallet
import schemas
from api.api_v1.deps import SessionDep
from core import constants
from models import PointDistributionHistory, Vault
from models.vault_performance import VaultPerformance
from models.vaults import NetworkChain, VaultCategory, VaultGroup, VaultMetadata
from schemas.pps_history_response import PricePerShareHistoryResponse
from schemas.vault import GroupSchema, SupportedNetwork, VaultExtended
from schemas.vault_metadata_response import VaultMetadataResponse
from services import kelpgain_service
from core.config import settings
from services.vault_rewards_service import VaultRewardsService

router = APIRouter()


def _update_vault_apy(vault: Vault, session: Session) -> schemas.Vault:
    schema_vault = schemas.Vault.model_validate(vault)
    if vault.strategy_name == constants.OPTIONS_WHEEL_STRATEGY:
        schema_vault.apy = vault.ytd_apy
    else:
        schema_vault.apy = vault.monthly_apy
    return schema_vault


def _get_last_price_per_share(session: Session, vault_id: uuid.UUID) -> float:
    latest_pps = session.exec(
        select(PricePerShareHistory)
        .where(PricePerShareHistory.vault_id == vault_id)
        .order_by(PricePerShareHistory.datetime.desc())
    ).first()

    return latest_pps.price_per_share if latest_pps else 0.0


def get_vault_earned_point_by_partner(
    session: Session, vault: Vault, partner_name: str
) -> PointDistributionHistory:
    """
    Get the latest PointDistributionHistory record for the given vault_id and partner name.

    If the partner name is 'HARMONIX', it also includes points from 'HARMONIX_MKT'.

    Args:
        session (Session): The database session used to execute queries.
        vault (Vault): The vault instance for which the points are being retrieved.
        partner_name (str): The name of the partner for which to retrieve the points.

    Returns:
        PointDistributionHistory: The latest PointDistributionHistory record for the specified vault and partner.
        If no record is found, a new instance is returned with zero points.
    """

    statement = (
        select(PointDistributionHistory)
        .where(
            PointDistributionHistory.vault_id == vault.id,
            PointDistributionHistory.partner_name == partner_name,
        )
        .order_by(PointDistributionHistory.created_at.desc())
    )
    point_dist_hist = session.exec(statement).first()

    mkt_point: float = 0
    if partner_name == constants.HARMONIX:
        statement_mtk = (
            select(PointDistributionHistory.point)
            .where(
                PointDistributionHistory.vault_id == vault.id,
                PointDistributionHistory.partner_name == constants.HARMONIX_MKT,
            )
            .order_by(PointDistributionHistory.created_at.desc())
        )
        point_dist_hist_mkt = session.exec(statement_mtk).first()
        mkt_point = point_dist_hist_mkt if point_dist_hist_mkt else 0

    if point_dist_hist is None:
        if partner_name == constants.HARMONIX:
            return PointDistributionHistory(
                vault_id=vault.id, partner_name=constants.HARMONIX, point=mkt_point
            )
        return PointDistributionHistory(
            vault_id=vault.id, partner_name=partner_name, point=0.0
        )

    if partner_name == constants.HARMONIX:
        point_dist_hist.point += mkt_point

    return point_dist_hist


def _get_vault_earned_reward_by_partner(
    session: Session, vault: Vault, partner_name: str
) -> RewardDistributionHistory:
    """
    Retrieve the latest RewardDistributionHistory record for a given vault and partner.

    Args:
        session (Session): The database session.
        vault (Vault): The vault instance.
        partner_name (str): The partner name.

    Returns:
        RewardDistributionHistory: The latest reward distribution history record. Returns a new instance with zero reward if no records are found.
    """
    statement = (
        select(RewardDistributionHistory)
        .where(
            RewardDistributionHistory.vault_id == vault.id,
            RewardDistributionHistory.partner_name == partner_name,
        )
        .order_by(RewardDistributionHistory.created_at.desc())
    )
    reward_dist_hist = session.exec(statement).first()
    return reward_dist_hist


def _get_name_token_reward(session: Session, vault: Vault) -> str:
    """
    Retrieve the reward token name for a given vault.

    Args:
        session (Session): The database session.
        vault (Vault): The vault instance.

    Returns:
        str: The reward token name. Returns an empty string if no reward token is found.
    """
    statement = select(RewardDistributionConfig.reward_token).where(
        RewardDistributionConfig.vault_id == vault.id
    )
    reward_token = session.exec(statement).first()

    return reward_token


def get_earned_points(session: Session, vault: Vault) -> List[schemas.EarnedPoints]:
    routes = json.loads(vault.routes) if vault.routes is not None else []
    partners = routes + [constants.HARMONIX]

    if vault.network_chain == NetworkChain.base:
        partners.append(constants.BSX)

    if vault.strategy_name == constants.PENDLE_HEDGING_STRATEGY:
        if vault.slug == constants.PENDLE_RSETH_26DEC24_SLUG:
            partners.append(constants.HYPERLIQUID)

    if vault.slug == constants.KELPDAO_GAIN_VAULT_SLUG:
        kelpgain_partners = [
            constants.EARNED_POINT_LINEA,
            constants.EARNED_POINT_SCROLL,
            constants.EARNED_POINT_KARAK,
            constants.EARNED_POINT_INFRA_PARTNER,
        ]
        partners.extend(kelpgain_partners)

    earned_points = []
    for partner in partners:
        point_dist_hist = get_vault_earned_point_by_partner(session, vault, partner)

        if partner != constants.PARTNER_KELPDAOGAIN:
            earned_points.append(
                schemas.EarnedPoints(
                    name=point_dist_hist.partner_name,
                    point=point_dist_hist.point,
                    created_at=point_dist_hist.created_at,
                )
            )

    return earned_points


def get_earned_rewards(session: Session, vault: Vault) -> List[schemas.EarnedRewards]:

    earned_rewards = []
    if vault.slug in [
        constants.PENDLE_RSETH_26JUN25_SLUG,
        # constants.HYPE_DELTA_NEUTRAL_SLUG,
    ]:
        reward = _get_vault_earned_reward_by_partner(session, vault, constants.HARMONIX)
        token_reward = _get_name_token_reward(session=session, vault=vault)
        if reward:
            earned_rewards.append(
                schemas.EarnedRewards(
                    name=token_reward,
                    rewards=reward.total_reward,
                    created_at=reward.created_at,
                )
            )
        else:
            earned_rewards.append(
                schemas.EarnedRewards(
                    name=token_reward,
                    rewards=0,
                    created_at=datetime.now(),
                )
            )

    return earned_rewards


@router.get("/", response_model=List[schemas.VaultExtended])
async def get_all_vaults(
    session: SessionDep,
    category: VaultCategory = Query(None),
    network_chain: NetworkChain = Query(None),
    tags: Optional[List[str]] = Query(None),
    sort_by: str = Query(
        "order", description="Sort field: 'order', 'tvl_desc', 'tvl_asc'"
    ),
):
    statement = select(Vault).where(Vault.is_active == True).order_by(Vault.order)

    conditions = []
    if category:
        conditions.append(Vault.category == category)

    if network_chain:
        conditions.append(Vault.network_chain == network_chain)

    if tags:
        # Adjust the filter for tags stored as a serialized string
        tags_conditions = [Vault.tags.contains(tag) for tag in tags]
        conditions.append(or_(*tags_conditions))
    else:
        conditions.append(~Vault.tags.contains("ended"))

    if conditions:
        statement = statement.where(and_(*conditions))

    vaults = session.exec(statement).all()
    results = []

    groups = session.exec(select(VaultGroup)).all()
    group_dict = {group.id: group.name for group in groups}
    for vault in vaults:
        group_id = vault.group_id or vault.id
        schema_vault = _update_vault_apy(vault, session=session)
        schema_vault.points = get_earned_points(session, vault)
        schema_vault.rewards = get_earned_rewards(session, vault)

        schema_vault.price_per_share = _get_last_price_per_share(
            session=session, vault_id=vault.id
        )

        for vault_metata in vault.vault_metadata:
            result = schemas.VaultExtended.model_validate(schema_vault)
            result.deposit_token = (vault_metata.deposit_token.split(","),)
            result.group_name = group_dict.get(group_id, "")
            results.append(result)

    if sort_by == "tvl_desc":
        results.sort(key=lambda x: float(x.tvl or 0), reverse=True)
    elif sort_by == "tvl_asc":
        results.sort(key=lambda x: float(x.tvl or 0))
    return results
