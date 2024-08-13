from datetime import datetime, timedelta
import json
from typing import List

from fastapi import APIRouter, HTTPException
from sqlalchemy import distinct, func
from sqlmodel import select
from models.pps_history import PricePerShareHistory
from models.user import User
from models.user_portfolio import UserPortfolio
from models.vault_performance import VaultPerformance
import schemas
import pandas as pd
from api.api_v1.deps import SessionDep
from models import Vault
from core.config import settings
from core import constants
from services.market_data import get_price

router = APIRouter()


@router.get("/{vault_id}", response_model=schemas.Statistics)
async def get_all_statistics(session: SessionDep, vault_id: str):

    statement = select(Vault).where(Vault.id == vault_id)
    vault = session.exec(statement).first()

    statement = (
        select(VaultPerformance)
        .where(VaultPerformance.vault_id == vault_id)
        .order_by(VaultPerformance.datetime.desc())
    )
    performances = session.exec(statement).first()
    if performances is None:
        raise HTTPException(
            status_code=400,
            detail="The performances data not found in the database.",
        )

    pps_history = session.exec(
        select(PricePerShareHistory)
        .where(PricePerShareHistory.vault_id == vault_id)
        .order_by(PricePerShareHistory.datetime.desc())
    ).first()
    last_price_per_share = pps_history.price_per_share

    statistic = schemas.Statistics(
        name=vault.name,
        price_per_share=last_price_per_share,
        apy_1y=(
            performances.apy_ytd
            if vault.strategy_name == constants.OPTIONS_WHEEL_STRATEGY
            else performances.apy_1m
        ),
        total_value_locked=performances.total_locked_value,
        risk_factor=performances.risk_factor,
        unique_depositors=performances.unique_depositors,
        fee_structure=json.loads(performances.fee_structure),
        vault_address=vault.contract_address,
        manager_address=vault.owner_wallet_address,
        all_time_high_per_share=performances.all_time_high_per_share,
        total_shares=performances.total_shares,
        sortino_ratio=performances.sortino_ratio,
        downside_risk=performances.downside_risk,
        earned_fee=performances.earned_fee,
        vault_network_chain=vault.network_chain,
        slug=vault.slug,
    )
    return statistic


@router.get("/", response_model=schemas.DashboardStats)
async def get_dashboard_statistics(session: SessionDep):
    statement = (
        select(Vault).where(Vault.strategy_name != None).where(Vault.is_active == True)
    )
    vaults = session.exec(statement).all()

    grouped_vaults = {}
    tvl_in_all_vaults = 0
    tvl_composition = {}

    for vault in vaults:
        group_id = vault.group_id or vault.id
        if group_id not in grouped_vaults:
            grouped_vaults[group_id] = {
                "total_tvl": 0,
                "default_vault": None,
                "vaults": [],
            }

        grouped_vaults[group_id]["vaults"].append(vault)
        grouped_vaults[group_id]["total_tvl"] += vault.tvl or 0

        if (vault.vault_group and vault.vault_group.default_vault_id == vault.id) or (
            not vault.vault_group
        ):
            grouped_vaults[group_id]["default_vault"] = vault

    data = []
    for group in grouped_vaults.values():
        default_vault = group["default_vault"]
        total_tvl = group["total_tvl"]

        if not default_vault:
            continue  # skip if there's no default vault (shouldn't happen)

        statement = (
            select(VaultPerformance)
            .where(VaultPerformance.vault_id == default_vault.id)
            .order_by(VaultPerformance.datetime.desc())
        )
        performance = session.exec(statement).first()

        pps_history = session.exec(
            select(PricePerShareHistory)
            .where(PricePerShareHistory.vault_id == default_vault.id)
            .order_by(PricePerShareHistory.datetime.desc())
        ).first()

        last_price_per_share = pps_history.price_per_share if pps_history else 0

        statistic = schemas.VaultStats(
            name=default_vault.name,
            price_per_share=last_price_per_share,
            apy_1y=(
                performance.apy_ytd
                if default_vault.strategy_name == constants.OPTIONS_WHEEL_STRATEGY
                else performance.apy_1m
            ),
            risk_factor=performance.risk_factor,
            total_value_locked=total_tvl,
            slug=default_vault.slug,
            id=default_vault.id,
        )

        if default_vault.slug == constants.SOLV_VAULT_SLUG:
            current_price = get_price("BTCUSDT")
            tvl_in_all_vaults += total_tvl * current_price
        else:
            tvl_in_all_vaults += total_tvl
        tvl_composition[default_vault.name] = total_tvl
        data.append(statistic)

    for key in tvl_composition:
        tvl_composition[key] = (
            tvl_composition[key] / tvl_in_all_vaults if tvl_in_all_vaults > 0 else 0
        )

    # count all portfolio of vault
    statement = select(func.count(distinct(UserPortfolio.user_address))).select_from(
        UserPortfolio
    )
    count = session.scalar(statement)

    dashboard_stats = schemas.DashboardStats(
        tvl_in_all_vaults=tvl_in_all_vaults,
        total_depositors=count,
        tvl_composition=tvl_composition,
        vaults=data,
    )
    return dashboard_stats


@router.get("/{vault_id}/tvl-history")
async def get_vault_performance(session: SessionDep, vault_id: str):
    # Get the VaultPerformance records for the given vault_id
    statement = select(Vault).where(Vault.id == vault_id)
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
        return {"date": [], "tvl": []}

    # Convert the list of VaultPerformance objects to a DataFrame
    pps_history_df = pd.DataFrame([vars(rec) for rec in perf_hist])

    # Rename the datetime column to date
    pps_history_df.rename(columns={"datetime": "date"}, inplace=True)

    pps_history_df["tvl"] = pps_history_df["total_locked_value"]

    # Convert the date column to string format
    pps_history_df["date"] = pps_history_df["date"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    pps_history_df.fillna(0, inplace=True)

    # Convert the DataFrame to a dictionary and return it
    return pps_history_df[["date", "tvl"]].to_dict(orient="list")


@router.get("/{days}/deposit-amount")
async def get_deposit(session: SessionDep, days: int):
    statement = (
        select(Vault).where(Vault.strategy_name != None).where(Vault.is_active == True)
    )
    
    vaults = session.exec(statement).all()
    
    total_locked_value_sum = 0
    days_ago = datetime.now() - timedelta(days=int(days))
    for vault in vaults:
        total_locked_value = session.exec(
            select(func.sum(VaultPerformance.total_locked_value))
            .where(VaultPerformance.vault_id == vault.id)
            .where(VaultPerformance.datetime >= days_ago)  
        ).first()
        
        if total_locked_value is not None:
            total_locked_value_sum += total_locked_value
  
    return total_locked_value_sum


@router.get("/{days}/total-user")
async def get_total_user(session: SessionDep, days: int):
    days_ago = datetime.now() - timedelta(days=int(days))
    statement = (
        select(func.count(User.user_id)).where(VaultPerformance.datetime >= days_ago)
    )
    
    total_user = session.exec(statement).first()
    
    return total_user

@router.get("/{days}/tvl/chart")
async def get_tvl__chart(session: SessionDep, days: int):
    days_ago = datetime.now() - timedelta(days=int(days))
    statement = (
        select(Vault).where(Vault.strategy_name != None).where(Vault.is_active == True)
    ) 
    vaults = session.exec(statement).all()
    
    results = []
    for vault in vaults:
        vault_performance = session.exec(
            select(VaultPerformance)
            .where(VaultPerformance.vault_id == vault.id)
            .where(VaultPerformance.datetime >= days_ago)  
            .order_by(VaultPerformance.datetime.desc())
        ).first()
        
        if vault_performance is not None:
            results.append({ 
                "vault_id": vault_performance.vault_id,           
                "total_locked_value": vault_performance.total_locked_value,
                "datetime": vault_performance.datetime
            })
    df = pd.DataFrame(results, columns=["datetime", "vault_id", "total_locked_value"])
     
    return df.to_dict(orient="records")