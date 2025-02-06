from datetime import datetime, timedelta, timezone
from itertools import groupby
import json
from operator import itemgetter
import traceback
from typing import List
import uuid

from fastapi import APIRouter, HTTPException
import pytz
from sqlalchemy import distinct, func, text
from sqlmodel import select
from models.deposit_summary_snapshot import DepositSummarySnapshot
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
from services.market_data import get_klines, get_price
from services.vault_contract_service import VaultContractService
from services.vault_performance_history_service import VaultPerformanceHistoryService
from utils.extension_utils import (
    to_amount_pendle,
    to_tx_aumount,
    to_tx_aumount_goldlink,
    to_tx_aumount_rethink,
)
from pytz import timezone

from utils.vault_utils import get_deposit_method_ids, get_vault_currency_price

router = APIRouter()


def __get_total_depositors(session: SessionDep) -> int:
    method_ids = get_deposit_method_ids()
    formatted_method_ids = ", ".join(f"'{method_id}'" for method_id in method_ids)

    raw_query = text(
        f"""
        SELECT 
            SUM(total_depositors) AS total_depositors_final
        FROM (
            SELECT 
                COUNT(DISTINCT from_address) AS total_depositors
            FROM 
                public.onchain_transaction_history
            WHERE 
                method_id IN ({formatted_method_ids})
            GROUP BY 
                to_timestamp("timestamp")::date
        ) AS daily_totals;
        """
    )

    result = session.exec(raw_query).scalar()

    return int(result) if result is not None else 0


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
    if pps_history:
        last_price_per_share = pps_history.price_per_share
    else:
        last_price_per_share = 0

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
        fee_structure=(
            json.loads(performances.fee_structure)
            if performances.fee_structure is not None
            else {}
        ),
        vault_address=vault.contract_address,
        manager_address=vault.owner_wallet_address,
        all_time_high_per_share=(
            performances.all_time_high_per_share
            if performances.all_time_high_per_share != None
            else 0
        ),
        total_shares=(
            performances.total_shares if performances.total_shares != None else 0
        ),
        sortino_ratio=performances.sortino_ratio,
        downside_risk=performances.downside_risk,
        earned_fee=performances.earned_fee if performances.earned_fee != None else 0,
        vault_network_chain=vault.network_chain,
        slug=vault.slug,
    )
    return statistic


@router.get("/", response_model=schemas.DashboardStats)
async def get_dashboard_statistics(session: SessionDep):
    statement = (
        select(Vault)
        .where(Vault.strategy_name != None)
        .where(Vault.is_active == True)
        .where(
            (Vault.tags == None) | (~Vault.tags.like("%ended%"))
        )  # Exclude vaults with 'ended' tag
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
        try:
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

            current_price = get_vault_currency_price(default_vault.vault_currency)
            tvl_in_all_vaults += total_tvl * current_price

            tvl_composition[default_vault.name] = total_tvl * current_price
            data.append(statistic)
        except Exception as e:
            print(f"Failed to calculate stats for {vault.id}, {vault.name}")
            print(traceback.format_exc())

    # count all portfolio of vault
    count = __get_total_depositors(session=session)
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


@router.get("/users/recent")
async def get_total_user(session: SessionDep):
    # Define the SQL query to get the total user count for 7 days, and 30 days
    raw_query = text(
        """
        SELECT
            SUM(CASE WHEN created_at >= (CURRENT_TIMESTAMP - INTERVAL '7 days') THEN 1 ELSE 0 END) AS total_user_7_days,
            SUM(CASE WHEN created_at >= (CURRENT_TIMESTAMP - INTERVAL '30 days') THEN 1 ELSE 0 END) AS total_user_30_days
        FROM
            users;
        """
    )

    result = session.exec(raw_query).one()

    # Return the results for 7 days, and 30 days
    return {
        "total_user_7_days": (
            0 if result.total_user_7_days is None else result.total_user_7_days
        ),
        "total_user_30_days": (
            0 if result.total_user_30_days is None else result.total_user_30_days
        ),
    }


@router.get("/depositors/recent")
async def get_total_depositors(session: SessionDep):
    # Prepare the method IDs for the SQL query
    method_ids = get_deposit_method_ids()
    formatted_method_ids = ", ".join(f"'{method_id}'" for method_id in method_ids)

    raw_query = text(
        f"""
        WITH unique_from_addresses_7_days AS (
            SELECT DISTINCT ON (from_address) from_address
            FROM public.onchain_transaction_history
            WHERE method_id IN ({formatted_method_ids})
              AND "timestamp" >= EXTRACT(EPOCH FROM NOW() - INTERVAL '7 days')
            ORDER BY from_address, "timestamp"
        ),
        unique_from_addresses_30_days AS (
            SELECT DISTINCT ON (from_address) from_address
            FROM public.onchain_transaction_history
            WHERE method_id IN ({formatted_method_ids})
              AND "timestamp" >= EXTRACT(EPOCH FROM NOW() - INTERVAL '30 days')
            ORDER BY from_address, "timestamp"
        )
        SELECT
            (SELECT COUNT(*) FROM unique_from_addresses_7_days) AS total_deposit_7_days,
            (SELECT COUNT(*) FROM unique_from_addresses_30_days) AS total_deposit_30_days;
        """
    )

    result = session.exec(raw_query).one()

    # Return the results for 7 days and 30 days
    return {
        "total_depositors_7_days": (
            0 if result.total_deposit_7_days is None else result.total_deposit_7_days
        ),
        "total_depositors_30_days": (
            0 if result.total_deposit_30_days is None else result.total_deposit_30_days
        ),
    }


@router.get("/yield/summary")
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
                and v.id <> 'd89eec0e-0850-4baf-ab24-53039ab47d0a'
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
        "yield_1_day": 0 if result.total_1d is None else result.total_1d,
        "yield_7_days": 0 if result.total_7d is None else result.total_7d,
        "yield_30_days": 0 if result.total_30d is None else result.total_30d,
    }


@router.get("/users/weekly-summary")
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


@router.get("/users/cumulative-summary")
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


@router.get("/tvl/weekly-chart")
async def get_vault_performance(session: SessionDep):
    raw_query = text(
        """
        SELECT 
            DATE_TRUNC('week', vp.datetime) AS date, 
            SUM(vp.total_locked_value) AS tvl
        FROM 
            vault_performance vp
        INNER JOIN 
            vaults v ON v.id = vp.vault_id
        WHERE 
            v.is_active = TRUE
        GROUP BY 
            date
        ORDER BY 
            date ASC;
        """
    )

    # Execute the query
    result = session.exec(raw_query).all()

    if len(result) == 0:
        return {"date": [], "tvl": []}

    # Convert the query result to a DataFrame
    pps_history_df = pd.DataFrame(result, columns=["date", "tvl"])

    # Convert the date column to string format for the response
    pps_history_df["date"] = pps_history_df["date"].dt.strftime("%Y-%m-%dT%H:%M:%S")

    # Convert the DataFrame to a dictionary and return it
    return pps_history_df[["date", "tvl"]].to_dict(orient="list")


@router.get("/tvl/cumulative-chart")
async def get_cumulative_vault_performance(session: SessionDep):
    # Define the SQL query to sum tvl values by day
    raw_query = text(
        """
        SELECT 
            DATE(vp.datetime) AS date, 
            SUM(vp.total_locked_value) AS tvl
        FROM 
            vault_performance vp
        INNER JOIN 
            vaults v ON v.id = vp.vault_id
        WHERE 
            v.is_active = TRUE
        GROUP BY 
            DATE(vp.datetime)
        ORDER BY 
            date ASC;
        """
    )

    # Execute the query
    result = session.exec(raw_query).all()

    if len(result) == 0:
        return {"date": [], "cumulative_tvl": []}

    # Convert the query result to a DataFrame
    pps_history_df = pd.DataFrame(result, columns=["date", "tvl"])

    # Convert the date column to datetime format for sorting and proper handling
    pps_history_df["date"] = pd.to_datetime(pps_history_df["date"])

    # Sort by date to ensure proper cumulative calculation
    pps_history_df = pps_history_df.sort_values(by="date")

    # Calculate the cumulative sum for the tvl column
    pps_history_df["cumulative_tvl"] = pps_history_df["tvl"].cumsum()

    # Convert the date column to string format for the response
    pps_history_df["date"] = pps_history_df["date"].dt.strftime("%Y-%m-%dT%H:%M:%S")

    # Convert the DataFrame to a dictionary and return it
    return pps_history_df[["date", "cumulative_tvl"]].to_dict(orient="list")


@router.get("/deposits/summary")
async def get_desposit_summary(session: SessionDep):
    # Define the SQL query to sum tvl values by day
    result = session.exec(
        select(DepositSummarySnapshot)
        .order_by(DepositSummarySnapshot.datetime.desc())
        .limit(1)
    ).first()

    return {
        "deposit_30_day": 0 if result is None else result.deposit_30_day,
        "deposit_7_day": 0 if result is None else result.deposit_7_day,
    }


@router.get("/api/yield-data-chart")
async def get_yield_chart_data(session: SessionDep):
    raw_query = text(
        """
          SELECT 
            DATE_TRUNC('week', vph.datetime) AS date,
            SUM(vph.total_locked_value) AS weekly_total_locked_value,
            SUM(SUM(vph.total_locked_value)) OVER (ORDER BY DATE_TRUNC('week', vph.datetime)) AS cumulative_total_locked_value
        FROM
            vault_performance_history vph
        INNER JOIN
            vaults v ON v.id = vph.vault_id
        WHERE
            v.is_active = TRUE and v.id <> 'd89eec0e-0850-4baf-ab24-53039ab47d0a'
        GROUP BY
            date
        ORDER BY
            date ASC;
        """
    )

    result = session.exec(raw_query)

    yield_data = [
        {"date": row[0], "weekly_yield": row[1], "cumulative_yield": row[2]}
        for row in result.all()
    ]

    return yield_data


@router.get("/api/user-data-chart")
async def get_user_chart_data(session: SessionDep):
    raw_query = text(
        """
        WITH user_stats AS (
            SELECT
                DATE(created_at) AS creation_date,
                COUNT(user_id) AS new_users
            FROM
                users
            GROUP BY
                DATE(created_at)
        )
        SELECT
            creation_date AS date,
            new_users,
            SUM(new_users) OVER (ORDER BY creation_date) AS cumulative_users
        FROM
            user_stats
        ORDER BY
            creation_date ASC
        """
    )

    result = session.exec(raw_query)

    yield_data = [
        {"date": row[0], "new_users": row[1], "cumulative_users": row[2]}
        for row in result.all()
    ]

    return yield_data


@router.get("/api/depositors-data-chart")
async def get_deposit_chart_data(session: SessionDep):
    # Prepare the method IDs for the SQL query
    method_ids = get_deposit_method_ids()
    formatted_method_ids = ", ".join(f"'{method_id}'" for method_id in method_ids)
    raw_query = text(
        f"""
        SELECT 
            to_timestamp("timestamp")::date AS date,
            COUNT(DISTINCT from_address) AS total_deposit,
            SUM(COUNT(DISTINCT from_address)) OVER (ORDER BY to_timestamp("timestamp")::date) AS cumulative_deposit
        FROM 
            public.onchain_transaction_history
        WHERE 
            method_id IN ({formatted_method_ids})
        GROUP BY 
            date
        ORDER BY 
            date;
        """
    )

    result = session.exec(raw_query).all()

    # Return the results as a list of dictionaries
    return [
        {
            "date": row.date,
            "total_depositors": (
                row.total_deposit if row.total_deposit is not None else 0
            ),
            "cumulative_depositors": (
                row.cumulative_deposit if row.cumulative_deposit is not None else 0
            ),
        }
        for row in result
    ]


@router.get("/api/tvl-data-chart")
async def get_tvl_chart_data(session: SessionDep):
    statement = select(Vault).where(Vault.is_active)
    vaults = session.exec(statement).all()

    # Create a mapping of vault_id to vault_currency
    vault_currencies = {vault.id: vault.vault_currency for vault in vaults}

    last_friday_for_daily_vault_raw_query = text(
        """
        SELECT DISTINCT ON (vp.vault_id, DATE_TRUNC('week', vp.datetime + INTERVAL '1 day')) 
            vp.vault_id,
            vp.total_locked_value,
            vp.datetime,
            v.vault_currency
        FROM vault_performance vp
        JOIN vaults v ON vp.vault_id = v.id
        WHERE v.id IN (
            SELECT id
            FROM vaults
            WHERE update_frequency = 'daily' and is_active = True
        )
        AND EXTRACT(DOW FROM vp.datetime) = 5
        """
    )

    result = session.exec(last_friday_for_daily_vault_raw_query)
    last_friday_for_daily_vaults = [
        {
            "vault_id": row[0],
            "tvl": row[1],
            "date": pd.to_datetime(row[2]).replace(
                hour=0, minute=0, second=0, microsecond=0
            ),
            "vault_currency": row[3],
        }
        for row in result.all()
    ]

    friday_vault_raw_query = text(
        """
        SELECT
            vp.vault_id,
            vp.total_locked_value,
            vp.datetime,
            v.vault_currency
        FROM vault_performance vp
        JOIN vaults v ON vp.vault_id = v.id
        WHERE v.id IN (
            SELECT id
            FROM vaults
            WHERE update_frequency = 'weekly' and is_active = True
        )
        AND EXTRACT(DOW FROM vp.datetime) = 5 
        """
    )
    result = session.exec(friday_vault_raw_query)
    friday_vaults = [
        {
            "vault_id": row[0],
            "tvl": row[1],
            "date": pd.to_datetime(row[2]).replace(
                hour=0, minute=0, second=0, microsecond=0
            ),
            "vault_currency": row[3],
        }
        for row in result.all()
    ]

    if last_friday_for_daily_vaults and friday_vaults:
        last_day_of_daily_vault = max(
            last_friday_for_daily_vaults, key=lambda x: x["date"]
        )["date"]

        last_day_of_weekly_vault = max(friday_vaults, key=lambda x: x["date"])["date"]

        if last_day_of_daily_vault > last_day_of_weekly_vault:
            friday_vaults.sort(key=itemgetter("vault_id", "date"))

            grouped_vaults = groupby(friday_vaults, key=itemgetter("vault_id"))

            last_daily_vaults = [
                max(vaults, key=itemgetter("date")) for _, vaults in grouped_vaults
            ]

            vault_add = []
            for vault in last_daily_vaults:
                vault_add.append(
                    {
                        "vault_id": vault["vault_id"],
                        "tvl": vault["tvl"],
                        "date": last_day_of_daily_vault,
                        "vault_currency": vault["vault_currency"]
                    }
                )

            friday_vaults.extend(vault_add)

    friday_vaults.sort(key=itemgetter("date"))
    last_friday_for_daily_vaults.sort(key=itemgetter("date"))
    joined_vaults = last_friday_for_daily_vaults + friday_vaults

    # Group TVLs by currency and date before converting to USD
    currency_grouped_vaults = {}
    for vault in joined_vaults:
        date = vault["date"]
        currency = vault.get("vault_currency", "USDC")
        
        if date not in currency_grouped_vaults:
            currency_grouped_vaults[date] = {}
        
        if currency not in currency_grouped_vaults[date]:
            currency_grouped_vaults[date][currency] = 0
            
        currency_grouped_vaults[date][currency] += vault["tvl"]

    # Calculate weekly changes in native currency amounts
    result = []
    sorted_dates = sorted(currency_grouped_vaults.keys())
    
    for i, date in enumerate(sorted_dates):
        current_tvl_usd = 0
        weekly_tvl_change_usd = 0
        
        for currency, amount in currency_grouped_vaults[date].items():
            current_price = get_vault_currency_price(currency)
            current_tvl_usd += amount * current_price
            
            if i > 0:
                prev_date = sorted_dates[i-1]
                prev_amount = currency_grouped_vaults[prev_date].get(currency, 0)
                
                # Calculate change in native currency amount
                native_change = amount - prev_amount
                # Convert change to USD at current price
                weekly_tvl_change_usd += native_change * current_price
        
        result.append({
            "date": date,
            "cumulative_tvl": current_tvl_usd,
            "weekly_tvl": weekly_tvl_change_usd
        })

    return result

