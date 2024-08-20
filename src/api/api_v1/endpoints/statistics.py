from datetime import datetime, timedelta
import json
from typing import List

from fastapi import APIRouter, HTTPException
from sqlalchemy import distinct, func, text
from sqlmodel import select
from models.pps_history import PricePerShareHistory
from models.user import User
from models.user_portfolio import UserPortfolio
from models.vault_performance import VaultPerformance
from models.vault_performance_history import VaultPerformanceHistory
import schemas
import pandas as pd
from api.api_v1.deps import SessionDep
from models import Vault
from core.config import settings
from core import constants
from services.deposit_service import DepositService
from services.market_data import get_price
from services.vault_performance_history_service import VaultPerformanceHistoryService
from utils.extension_utils import get_init_dates

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
async def get_vault_performance(
    session: SessionDep, vault_id: str, is_weekly: bool = False
):
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

    pps_history_df = pps_history_df[["date", "tvl"]]
    # Convert the date column to datetime format for resampling
    pps_history_df["date"] = pd.to_datetime(pps_history_df["date"])
    if is_weekly:
        # Resample the data to weekly sum
        pps_history_df.set_index("date", inplace=True)
        # Resample by week and calculate by lasted
        pps_history_df = pps_history_df.resample("W").last()
        pps_history_df.reset_index(inplace=True)

    # Convert the date column to string format for the response
    pps_history_df["date"] = pps_history_df["date"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    pps_history_df.fillna(0, inplace=True)

    # Convert the DataFrame to a dictionary and return it
    return pps_history_df[["date", "tvl"]].to_dict(orient="list")


@router.get("/users/total")
async def get_total_user(session: SessionDep):
    # Define the SQL query to get the total user count for 1 day, 7 days, and 30 days
    raw_query = text(
        """
        SELECT
            SUM(CASE WHEN created_at >= (CURRENT_TIMESTAMP - INTERVAL '7 days') THEN 1 ELSE 0 END) AS total_7d,
            SUM(CASE WHEN created_at >= (CURRENT_TIMESTAMP - INTERVAL '30 days') THEN 1 ELSE 0 END) AS total_30d
        FROM
            users;
        """
    )

    result = session.exec(raw_query).one()

    # Return the results for 1 day, 7 days, and 30 days
    return {
        "total_user_7_days": result.total_7d,
        "total_user_30_days": result.total_30d,
    }


@router.get("/yield/query")
async def get_yield(session: SessionDep):
    raw_query = text(
        """
         WITH vault_performance AS (
            SELECT
                v.id AS vault_id,
                v.strategy_name,
                v.is_active,
                p.total_locked_value,
                p.datetime
            FROM
                public.vaults v
            INNER JOIN
                public.vault_performance_history p ON v.id = p.vault_id
            WHERE
                v.strategy_name IS NOT NULL
                AND v.is_active = TRUE
                AND p.datetime BETWEEN (CURRENT_TIMESTAMP - INTERVAL '30 days') AND CURRENT_TIMESTAMP
        )
        SELECT
            SUM(CASE WHEN p.datetime BETWEEN (CURRENT_TIMESTAMP - INTERVAL '1 day') AND CURRENT_TIMESTAMP THEN p.total_locked_value ELSE 0 END) AS total_1d,
            SUM(CASE WHEN p.datetime BETWEEN (CURRENT_TIMESTAMP - INTERVAL '7 days') AND CURRENT_TIMESTAMP THEN p.total_locked_value ELSE 0 END) AS total_7d,
            SUM(CASE WHEN p.datetime BETWEEN (CURRENT_TIMESTAMP - INTERVAL '30 days') AND CURRENT_TIMESTAMP THEN p.total_locked_value ELSE 0 END) AS total_30d
        FROM
            vault_performance p;
        """
    )

    # Execute the query and retrieve the result
    result = session.exec(raw_query).one()

    # Return the results for 1 day, 7 days, and 30 days
    return {
        "yield_1_day": result.total_1d,
        "yield_7_days": result.total_7d,
        "yield_30_days": result.total_30d,
    }


@router.get("/weekly/new-users")
async def get_weekly_user(session: SessionDep):
    # Define the SQL query to calculate cumulative users by creation date
    raw_query = text(
        """
        SELECT
            EXTRACT(YEAR FROM created_at) AS year,
            EXTRACT(WEEK FROM created_at) AS week,
            COUNT(user_id) AS new_users
        FROM
            users
        GROUP BY
            EXTRACT(YEAR FROM created_at),
            EXTRACT(WEEK FROM created_at)
        ORDER BY
            year ASC,
            week ASC;
        """
    )

    # Execute the raw SQL query
    result = session.exec(raw_query)

    # Fetch all results as a list of dictionaries
    users = [
        {"year": row[0], "week": row[1], "new_users": row[2]} for row in result.all()
    ]

    return users


@router.get("/cumulative/new-users")
async def get_cumulative_user(session: SessionDep):
    # Define the SQL query to calculate cumulative users by creation date
    raw_query = text(
        """
        WITH daily_users AS (
            SELECT
                DATE(created_at) AS creation_date,
                COUNT(user_id) AS new_users
            FROM
                users
            GROUP BY
                DATE(created_at)
            ORDER BY
                creation_date
        )
        SELECT
            creation_date as date,
            SUM(new_users) OVER (ORDER BY creation_date) AS cumulative_users
        FROM
            daily_users;
        """
    )

    # Execute the raw SQL query
    result = session.exec(raw_query)

    # Fetch all results as a list of dictionaries
    cumulative_users = [
        {"date": row[0], "cumulative_users": row[1]} for row in result.all()
    ]

    return cumulative_users


@router.get("/{vault_id}/yield/daily-chart")
async def get_yield_daily_chart(session: SessionDep, vault_id: str):
    statement = select(Vault).where(Vault.id == vault_id)
    vault = session.exec(statement).first()
    if vault is None:
        raise HTTPException(
            status_code=400,
            detail="The data not found in the database.",
        )

    records = session.exec(
        select(VaultPerformanceHistory)
        .where(VaultPerformanceHistory.vault_id == vault.id)
        .order_by(VaultPerformanceHistory.datetime.desc())
    ).all()

    if len(records) == 0:
        return {"date": [], "tvl": []}

    df = pd.DataFrame([vars(rec) for rec in records])
    df.rename(columns={"datetime": "date"}, inplace=True)
    df.rename(columns={"total_locked_value": "tvl"}, inplace=True)
    df = df[["date", "tvl"]]

    return df[["date", "tvl"]].to_dict(orient="list")


@router.get("/{vault_id}/cumulative/daily-chart")
async def get_yield_cumulative_chart(session: SessionDep, vault_id: str):

    statement = select(Vault).where(Vault.id == vault_id)
    vault = session.exec(statement).first()
    if vault is None:
        raise HTTPException(
            status_code=400,
            detail="The data not found in the database.",
        )

    records = session.exec(
        select(VaultPerformanceHistory)
        .where(VaultPerformanceHistory.vault_id == vault.id)
        .order_by(VaultPerformanceHistory.datetime.desc())
    ).all()

    if len(records) == 0:
        return {"date": [], "tvl": []}

    df = pd.DataFrame([vars(rec) for rec in records])
    df.rename(columns={"datetime": "date"}, inplace=True)
    df.rename(columns={"total_locked_value": "tvl"}, inplace=True)
    df = df[["date", "tvl"]]

    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    df["tvl"] = df["tvl"].cumsum()
    df.reset_index(inplace=True)
    df["date"] = df["date"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    return df[["date", "tvl"]].to_dict(orient="list")
