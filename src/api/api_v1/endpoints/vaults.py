import json
from typing import List

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, and_, select

import schemas
from api.api_v1.deps import SessionDep
from core import constants
from models import PointDistributionHistory, Vault
from models.vault_performance import VaultPerformance
from models.vaults import NetworkChain, VaultCategory
from schemas.vault import GroupSchema

router = APIRouter()


def _update_vault_apy(vault: Vault) -> schemas.Vault:
    schema_vault = schemas.Vault.model_validate(vault)

    if vault.strategy_name == constants.OPTIONS_WHEEL_STRATEGY:
        schema_vault.apy = vault.ytd_apy
    else:
        schema_vault.apy = vault.monthly_apy
    return schema_vault


def get_vault_earned_point_by_partner(
    session: Session, vault: Vault, partner_name: str
) -> PointDistributionHistory:
    """
    Get the latest PointDistributionHistory record for the given vault_id
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
    if point_dist_hist is None:
        return PointDistributionHistory(
            vault_id=vault.id, partner_name=partner_name, point=0.0
        )
    return point_dist_hist


def get_earned_points(session: Session, vault: Vault) -> List[schemas.EarnedPoints]:
    routes = (
        json.loads(vault.routes) + [constants.EIGENLAYER]
        if vault.routes is not None
        else []
    )
    partners = routes + [
        constants.HARMONIX,
    ]

    if vault.network_chain == NetworkChain.base:
        partners.append(constants.BSX)

    earned_points = []
    for partner in partners:
        point_dist_hist = get_vault_earned_point_by_partner(session, vault, partner)
        if point_dist_hist is not None:
            earned_points.append(
                schemas.EarnedPoints(
                    name=partner,
                    point=point_dist_hist.point,
                    created_at=point_dist_hist.created_at,
                )
            )
        else:
            # add default value 0
            earned_points.append(
                schemas.EarnedPoints(
                    name=partner,
                    point=0.0,
                    created_at=None,
                )
            )

    return earned_points


@router.get("/", response_model=List[schemas.GroupSchema])
async def get_all_vaults(
    session: SessionDep,
    category: VaultCategory = Query(None),
    network_chain: NetworkChain = Query(None),
):
    statement = select(Vault).where(Vault.is_active == True).order_by(Vault.order)
    if category or network_chain:
        conditions = []
        if category:
            conditions.append(Vault.category == category)
        if network_chain:
            conditions.append(Vault.network_chain == network_chain)
        statement = statement.where(and_(*conditions))

    vaults = session.exec(statement).all()

    grouped_vaults = {}
    for vault in vaults:
        group_id = vault.group_id or vault.id
        schema_vault = _update_vault_apy(vault)
        schema_vault.points = get_earned_points(session, vault)
        if group_id not in grouped_vaults:
            if (
                vault.vault_group and vault.vault_group.default_vault_id == vault.id
            ) or (not vault.vault_group):
                schema_vault.is_default = True

            grouped_vaults[group_id] = {
                "id": group_id,
                "name": vault.vault_group.name if vault.vault_group else vault.name,
                "tvl": schema_vault.tvl or 0,
                "apy": schema_vault.apy or 0,
                "default_vault_id": (
                    vault.vault_group.default_vault_id if vault.vault_group else None
                ),
                "vaults": [schema_vault],
                "points": {},
            }
        else:
            grouped_vaults[group_id]["vaults"].append(schema_vault)
            grouped_vaults[group_id]["tvl"] += vault.tvl or 0
            grouped_vaults[group_id]["apy"] = max(
                grouped_vaults[group_id]["apy"], vault.ytd_apy or 0
            )

        # Aggregate points for each partner
        for point in schema_vault.points:
            if point.name in grouped_vaults[group_id]["points"]:
                grouped_vaults[group_id]["points"][point.name] += point.point
            else:
                grouped_vaults[group_id]["points"][point.name] = point.point

    groups = [
        GroupSchema(
            id=group["id"],
            name=group["name"],
            tvl=group["tvl"],
            apy=group["apy"],
            vaults=group["vaults"],
            points=[
                schemas.EarnedPoints(name=partner, point=points)
                for partner, points in group["points"].items()
            ],
        )
        for group in grouped_vaults.values()
    ]

    return groups


@router.get("/{vault_slug}", response_model=schemas.Vault)
async def get_vault_info(session: SessionDep, vault_slug: str):
    statement = select(Vault).where(Vault.slug == vault_slug)
    vault = session.exec(statement).first()
    if vault is None:
        raise HTTPException(
            status_code=400,
            detail="The data not found in the database.",
        )

    schema_vault = _update_vault_apy(vault)
    schema_vault.points = get_earned_points(session, vault)

    # Check if the vault is part of a group
    if vault.vault_group:
        # Query all vaults in the group
        group_vaults_statement = select(Vault).where(Vault.group_id == vault.group_id)
        group_vaults = session.exec(group_vaults_statement).all()

        # Get the selected network chain of all vaults in the group
        selected_networks = {v.network_chain for v in group_vaults if v.network_chain}
        schema_vault.supported_network = list(selected_networks)
    else:
        # If the vault doesn't have a group, get the network of this vault
        schema_vault.supported_network = [vault.network_chain] if vault.network_chain else []

    return schema_vault


@router.get("/{vault_slug}/performance")
async def get_vault_performance(session: SessionDep, vault_slug: str):
    # Get the VaultPerformance records for the given vault_id
    statement = select(Vault).where(Vault.slug == vault_slug)
    vault = session.exec(statement).first()
    if vault is None:
        raise HTTPException(
            status_code=400,
            detail="The data not found in the database.",
        )

    perf_hist = session.exec(
        select(VaultPerformance)
        .where(VaultPerformance.vault_id == vault.id)
        .order_by(VaultPerformance.datetime.asc())
    ).all()
    if len(perf_hist) == 0:
        return {"date": [], "apy": []}

    # Convert the list of VaultPerformance objects to a DataFrame
    pps_history_df = pd.DataFrame([vars(rec) for rec in perf_hist])

    # Rename the datetime column to date
    pps_history_df.rename(columns={"datetime": "date"}, inplace=True)

    if vault.strategy_name == constants.DELTA_NEUTRAL_STRATEGY:
        pps_history_df["apy"] = pps_history_df["apy_1m"]

        if vault.network_chain in {NetworkChain.arbitrum_one, NetworkChain.base}:
            pps_history_df = pps_history_df[["date", "apy"]].copy()

            # resample pps_history_df to daily frequency
            pps_history_df["date"] = pd.to_datetime(pps_history_df["date"])
            pps_history_df.set_index("date", inplace=True)
            pps_history_df = pps_history_df.resample("D").mean()
            pps_history_df.ffill(inplace=True)

            if (
                len(pps_history_df) >= 7 * 2
            ):  # we will make sure the normalized series enough to plot
                # calculate ma 7 days pps_history_df['apy']
                pps_history_df["apy"] = pps_history_df["apy"].rolling(window=7).mean()

    elif vault.strategy_name == constants.OPTIONS_WHEEL_STRATEGY:
        pps_history_df["apy"] = pps_history_df["apy_ytd"]

    # Convert the date column to string format
    pps_history_df.reset_index(inplace=True)
    pps_history_df["date"] = pps_history_df["date"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    pps_history_df.fillna(0, inplace=True)

    # Convert the DataFrame to a dictionary and return it
    return pps_history_df[["date", "apy"]].to_dict(orient="list")
