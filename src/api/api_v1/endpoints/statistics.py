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
    session: SessionDep, vault_id: str, isWeekly: bool = False
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
    if isWeekly:
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


@router.get("/deposit/total-amount")
async def get_deposit(session: SessionDep, days: int):
    statement = (
        select(Vault).where(Vault.strategy_name != None).where(Vault.is_active == True)
    )

    vaults = session.exec(statement).all()

    total_locked_value_sum = 0
    end_date = datetime.now()
    start_date = end_date - timedelta(days=int(days))
    service = DepositService(session)
    for vault in vaults:
        total_locked_value_sum += service.get_total_deposits(
            vault, start_date.timestamp(), end_date.timestamp()
        )

    return total_locked_value_sum


@router.get("/{days}/total-user")
async def get_total_user(session: SessionDep, days: int):
    days_ago = datetime.now() - timedelta(days=int(days))
    statement = select(func.count(User.user_id)).where(User.created_at >= days_ago)

    total_user = session.exec(statement).first()

    return total_user


@router.get("/yield/query")
async def get_deposit(session: SessionDep, days):
    statement = (
        select(Vault).where(Vault.strategy_name != None).where(Vault.is_active == True)
    )
    vaults = session.exec(statement).all()

    service = VaultPerformanceHistoryService(session)
    result = 0
    end_date = datetime.now()
    start_date = end_date - timedelta(days=int(days))
    for vault in vaults:
        vault_performance_histories = service.get_by(vault.id, start_date, end_date)
        yield_data = sum(tx.total_locked_value for tx in vault_performance_histories)
        result += float(yield_data)

    return result


@router.get("/weekly/new-users")
async def get_weekly_user(session: SessionDep):
    users = session.exec(select(User).order_by(User.created_at.asc())).all()

    if len(users) == 0:
        return {"date": [], "total": []}

    user_df = pd.DataFrame([vars(rec) for rec in users])

    user_df.rename(columns={"created_at": "date"}, inplace=True)
    user_df = user_df[["date", "wallet_address"]]
    user_df["date"] = pd.to_datetime(user_df["date"])

    user_df.set_index("date", inplace=True)
    user_df = user_df.resample("W").count()
    user_df.reset_index(inplace=True)
    user_df.rename(columns={"wallet_address": "total"}, inplace=True)

    user_df["date"] = user_df["date"].dt.strftime("%Y-%m-%dT%H:%M:%S")

    return user_df[["date", "total"]].to_dict(orient="list")


@router.get("/cumulative/new-users")
async def get_cumulative_user(session: SessionDep):
    # Get all users ordered by creation date
    users = session.exec(select(User).order_by(User.created_at.asc())).all()

    if len(users) == 0:
        return {"date": [], "total": []}

    # Convert list of User objects to DataFrame
    user_df = pd.DataFrame([vars(rec) for rec in users])
    user_df.rename(columns={"created_at": "date"}, inplace=True)
    user_df = user_df[["date", "wallet_address"]]

    user_df["date"] = pd.to_datetime(user_df["date"])
    user_df.set_index("date", inplace=True)

    # Resample by day and count the number of users per day
    user_df = user_df.resample("D").count()

    user_df["total"] = user_df["wallet_address"].cumsum()
    user_df.reset_index(inplace=True)
    user_df.rename(columns={"wallet_address": "daily_count"}, inplace=True)

    # Convert 'date' column to string format
    user_df["date"] = user_df["date"].dt.strftime("%Y-%m-%dT%H:%M:%S")

    # Return the result as a dictionary
    return user_df[["date", "total"]].to_dict(orient="list")


def get_vault_performance_dates() -> List[datetime]:
    start_date = datetime(2024, 3, 1)
    end_date = datetime.now() - timedelta(days=1)

    date_list = []
    current_date = start_date

    while current_date <= end_date:
        date_list.append(current_date)
        current_date += timedelta(days=1)

    return date_list


@router.get("/yield/daily-chart")
async def get_yield_daily_chart(session: SessionDep):
    statement = (
        select(Vault).where(Vault.strategy_name != None).where(Vault.is_active == True)
    )
    vaults = session.exec(statement).all()

    vault_performance_dates = get_init_dates()

    daily_totals = []

    for date in vault_performance_dates:
        total_locked_value_for_day = 0

        for vault in vaults:
            if vault.network_chain == constants.CHAIN_ETHER_MAINNET:
                if date.weekday() == 4:
                    record = session.exec(
                        select(VaultPerformanceHistory)
                        .where(VaultPerformanceHistory.vault_id == vault.id)
                        .where(VaultPerformanceHistory.datetime == date)
                        .order_by(VaultPerformanceHistory.datetime.desc())
                    ).first()

                else:
                    prev_friday = date - timedelta(days=(date.weekday() - 4) % 7)
                    record = session.exec(
                        select(VaultPerformanceHistory)
                        .where(VaultPerformanceHistory.vault_id == vault.id)
                        .where(VaultPerformanceHistory.datetime == prev_friday)
                        .order_by(VaultPerformanceHistory.datetime.desc())
                    ).first()

            else:
                record = session.exec(
                    select(VaultPerformanceHistory)
                    .where(VaultPerformanceHistory.vault_id == vault.id)
                    .where(VaultPerformanceHistory.datetime == date)
                    .order_by(VaultPerformanceHistory.datetime.desc())
                ).first()

            if record:
                total_locked_value_for_day += record.total_locked_value
        daily_totals.append({"date": date, "tvl": total_locked_value_for_day})

    df = pd.DataFrame(daily_totals)
    return df[["date", "tvl"]].to_dict(orient="list")


@router.get("/cumulative/daily-chart")
async def get_yield_cumulative_chart(session: SessionDep):
    statement = (
        select(Vault).where(Vault.strategy_name != None).where(Vault.is_active == True)
    )
    vaults = session.exec(statement).all()

    vault_performance_dates = get_init_dates()

    daily_totals = []

    for date in vault_performance_dates:
        total_locked_value_for_day = 0

        for vault in vaults:
            if vault.network_chain == constants.CHAIN_ETHER_MAINNET:
                if date.weekday() == 4:
                    record = session.exec(
                        select(VaultPerformanceHistory)
                        .where(VaultPerformanceHistory.vault_id == vault.id)
                        .where(VaultPerformanceHistory.datetime == date)
                        .order_by(VaultPerformanceHistory.datetime.desc())
                    ).first()

                else:
                    prev_friday = date - timedelta(days=(date.weekday() - 4) % 7)
                    record = session.exec(
                        select(VaultPerformanceHistory)
                        .where(VaultPerformanceHistory.vault_id == vault.id)
                        .where(VaultPerformanceHistory.datetime == prev_friday)
                        .order_by(VaultPerformanceHistory.datetime.desc())
                    ).first()

            else:
                record = session.exec(
                    select(VaultPerformanceHistory)
                    .where(VaultPerformanceHistory.vault_id == vault.id)
                    .where(VaultPerformanceHistory.datetime == date)
                    .order_by(VaultPerformanceHistory.datetime.desc())
                ).first()

            if record:
                total_locked_value_for_day += record.total_locked_value
        daily_totals.append({"date": date, "tvl": total_locked_value_for_day})

    df = pd.DataFrame(daily_totals)
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    df["tvl"] = df["tvl"].cumsum()
    df.reset_index(inplace=True)
    df["date"] = df["date"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    return df[["date", "tvl"]].to_dict(orient="list")
