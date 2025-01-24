import logging
from typing import List, Tuple
import uuid
from datetime import datetime, timedelta, timezone

import click
import pandas as pd
import pendulum
import seqlog
from sqlalchemy import func
from sqlmodel import Session, or_, select, not_
from web3 import Web3
from web3.contract import Contract

from bg_tasks.utils import (
    calculate_pps_statistics,
    calculate_roi,
    get_before_price_per_shares,
)
from core import constants
from core.abi_reader import read_abi
from core.config import settings
from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models import Vault
from models.apy_component import APYComponent
from models.pps_history import PricePerShareHistory
from models.reward_distribution_config import RewardDistributionConfig
from models.user_portfolio import UserPortfolio
from models.vault_apy_breakdown import VaultAPYBreakdown
from models.vault_performance import VaultPerformance
from models.vaults import NetworkChain, VaultCategory
from schemas.fee_info import FeeInfo
from schemas.vault_state import VaultState
from services.bsx_service import get_points_earned
from services.hyperliquid_service import (
    get_avg_8h_funding_rate,
)
from services.market_data import get_hl_price, get_price
from services.vault_rewards_service import VaultRewardsService
from utils.vault_utils import calculate_projected_apy
from utils.web3_utils import get_vault_contract, get_current_pps, get_current_tvl

# # Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("update_delta_neutral_vault_performance_daily")

session = Session(engine)
token_abi = read_abi("ERC20")


def update_tvl(vault_id: uuid.UUID, current_tvl: float):
    vault = session.exec(select(Vault).where(Vault.id == vault_id)).first()
    if vault:
        vault.tvl = current_tvl
        session.commit()


def get_price_per_share_history(vault_id: uuid.UUID) -> pd.DataFrame:
    pps_history = session.exec(
        select(PricePerShareHistory)
        .where(PricePerShareHistory.vault_id == vault_id)
        .order_by(PricePerShareHistory.datetime.asc())
    ).all()

    # Convert the list of PricePerShareHistory objects to a DataFrame
    pps_history_df = pd.DataFrame([vars(pps) for pps in pps_history])

    return pps_history_df[["datetime", "price_per_share", "vault_id"]]


def update_price_per_share(vault_id: uuid.UUID, current_price_per_share: float):
    # update today to hour with minute = 0 and second = 0
    today = pendulum.now(tz=pendulum.UTC).replace(minute=0, second=0, microsecond=0)

    # Check if a PricePerShareHistory record for today already exists
    existing_pps = session.exec(
        select(PricePerShareHistory).where(
            PricePerShareHistory.vault_id == vault_id,
            PricePerShareHistory.datetime == today,
        )
    ).first()

    if existing_pps:
        # If a record for today already exists, update the price per share
        existing_pps.price_per_share = current_price_per_share
    else:
        # If no record for today exists, create a new one
        new_pps = PricePerShareHistory(
            datetime=today, price_per_share=current_price_per_share, vault_id=vault_id
        )
        session.add(new_pps)

    session.commit()


def get_fee_info():
    fee_structure = [0, 0, 10, 1]
    fee_info = FeeInfo(
        deposit_fee=fee_structure[0],
        exit_fee=fee_structure[1],
        performance_fee=fee_structure[2],
        management_fee=fee_structure[3],
    )
    json_fee_info = fee_info.model_dump_json()
    return json_fee_info


def get_vault_state(vault_contract: Contract, owner_address: str, vault: Vault):
    state = vault_contract.functions.getVaultState().call(
        {"from": Web3.to_checksum_address(owner_address)}
    )

    if vault.slug == constants.GOLD_LINK_SLUG:
        vault_state = VaultState(
            withdraw_pool_amount=state[2] / 1e6,
            pending_deposit=state[3] / 1e6,
            total_share=state[4] / 1e6,
            total_fee_pool_amount=state[5] / 1e6,
            last_update_management_fee_date=state[6],
        )
    else:
        vault_state = VaultState(
            withdraw_pool_amount=state[0] / 1e6,
            pending_deposit=state[1] / 1e6,
            total_share=state[2] / 1e6,
            total_fee_pool_amount=state[3] / 1e6,
            last_update_management_fee_date=state[4],
        )
    return vault_state


def get_next_friday():
    today = pendulum.now(tz=pendulum.UTC)
    next_friday = today.next(pendulum.FRIDAY)
    next_friday = next_friday.replace(hour=8, minute=0, second=0, microsecond=0)
    return next_friday


def get_next_day():
    today = pendulum.now(tz=pendulum.UTC).today()
    next_day = today.add(days=1)
    next_day = next_day.replace(hour=8, minute=0, second=0, microsecond=0)
    return next_day


def calculate_apy_ytd(vault_id, current_price_per_share):
    now = pendulum.now(tz=pendulum.UTC)
    vault = session.exec(select(Vault).where(Vault.id == vault_id)).first()

    # Get the start of the year or the first logged price per share
    start_of_year = pendulum.datetime(now.year, 1, 1, tz="UTC")
    price_per_share_start = session.exec(
        select(PricePerShareHistory)
        .where(
            PricePerShareHistory.vault_id == vault.id
            and PricePerShareHistory.datetime >= start_of_year
        )
        .order_by(PricePerShareHistory.datetime.asc())
    ).first()

    prev_pps = price_per_share_start.price_per_share if price_per_share_start else 1

    # Calculate the APY
    apy_ytd = calculate_roi(
        current_price_per_share,
        prev_pps,
        days=(now - start_of_year).days,
    )

    return apy_ytd


def calculate_reward_distribution_progress(
    start_date: datetime, current_date: datetime
) -> float:
    """Calculate the progress of reward distribution within a week.
    Returns percentage (0-1) of the week that has elapsed."""
    week_start = pendulum.instance(start_date)
    current = pendulum.instance(current_date)

    # If current date is past week end, return 1 (100%)
    week_end = week_start.add(weeks=1)
    if current >= week_end:
        return 1.0

    # Calculate progress within the week
    total_week_seconds = (week_end - week_start).total_seconds()
    elapsed_seconds = (current - week_start).total_seconds()
    return max(0, min(1, elapsed_seconds / total_week_seconds))


def calculate_reward_apy(
    vault_id: uuid.UUID,
    total_tvl: float,
    day_ranges: List[int] = [7, 15, 30, 45],
    current_date: pendulum.DateTime | None = None
) -> Tuple[float, float, float, float]:
    """Calculate weekly and monthly reward APY based on distribution config."""
    if total_tvl <= 0:
        return 0.0, 0.0, 0, 0

    if current_date is None:
        current_date = pendulum.now(tz=pendulum.UTC)

    # Get all reward distributions
    reward_configs = session.exec(
        select(RewardDistributionConfig)
        .where(RewardDistributionConfig.vault_id == vault_id)
        .order_by(RewardDistributionConfig.start_date.asc())
    ).all()

    if not reward_configs:
        return 0.0, 0.0, 0, 0

    token_name = reward_configs[0].reward_token.replace("$", "")
    hype_price = get_hl_price(token_name)  # Get current HYPE token price

    # 1. Tìm ngày bắt đầu thật sự sớm nhất của campaign
    campaign_start_date = min(cfg.start_date for cfg in reward_configs)

    # Kết quả lưu APY cho mỗi day_range
    apy_results = {}

    for days in day_ranges:
        # 2. Xác định ngày bắt đầu tính reward, không vượt quá campaign_start_date
        raw_start_period = current_date - timedelta(days=days)
        start_period = max(raw_start_period, campaign_start_date)

        # Tính số ngày thực tế
        effective_days = (current_date - start_period).days
        if effective_days <= 0:
            # Nếu chưa có ngày nào để tính reward
            apy_results[days] = 0.0
            continue

        # Tổng reward kiếm được trong giai đoạn (start_period -> current_date)
        total_earned_in_period = 0.0

        for config in reward_configs:
            # Mỗi tuần được định nghĩa bắt đầu tại config.start_date
            week_start = config.start_date
            # Giả sử 1 tuần reward = 7 ngày
            week_end = week_start + timedelta(days=7)

            # Reward của tuần = total_reward * distribution_percentage (VD: 100 * 0.35 = 35)
            reward_for_this_week = (config.total_reward or 0.0) * (
                config.distribution_percentage or 0.0
            )
            reward_for_this_week *= hype_price

            # Tính overlap giữa khoảng [start_period, current_date] và [week_start, week_end]
            overlap_start = max(start_period, week_start)
            overlap_end = min(current_date, week_end)

            # Nếu có overlap (khoảng thời gian giao nhau dương)
            if overlap_end > overlap_start:
                # Tính phần trăm thời gian overlap trong 7 ngày của tuần này
                # total_week_days = (week_end - week_start).days  # thường = 7
                # overlap_days = (overlap_end - overlap_start).days

                # Tránh trường hợp do chênh lệch giờ, .days có thể chưa đủ chính xác
                # ta có thể dùng total_seconds() / (24*3600) thay thế nếu muốn chính xác tuyệt đối
                overlap_days = (overlap_end - overlap_start).total_seconds() / 86400.0
                total_week_days = (week_end - week_start).total_seconds() / 86400.0

                # Fraction of reward tương ứng với số ngày overlap
                fraction_of_week = overlap_days / total_week_days

                # Reward thực nhận cho phần overlap
                earned_reward_this_week = fraction_of_week * reward_for_this_week
                total_earned_in_period += earned_reward_this_week

        # 4. Annualize dựa trên effective_days (thay vì days)
        if total_tvl > 0 and effective_days > 0:
            apy = (total_earned_in_period / total_tvl) * (365 / effective_days) * 100
        else:
            apy = 0.0

        apy_results[days] = apy

    return apy_results[7], apy_results[30], apy_results[15], apy_results[45]


# Step 4: Calculate Performance Metrics
def calculate_performance(
    vault: Vault,
    vault_contract: Contract,
    owner_address: str,
    update_freq: str = "daily",
):
    current_price = get_price("ETHUSDT")

    # today = datetime.strptime(df["Date"].iloc[-1], "%Y-%m-%d")
    # today = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    today = datetime.now(timezone.utc)
    # candles = get_klines("ETHUSDT", end_time=(today + timedelta(days=2)), limit=1)
    # current_price = float(candles[0][4])

    # price_per_share_df = get_price_per_share_history(vault_id)

    current_price_per_share = get_current_pps(vault_contract)
    total_balance = get_current_tvl(vault_contract)
    fee_info = get_fee_info()
    vault_state = get_vault_state(
        vault_contract, owner_address=owner_address, vault=vault
    )

    if vault.slug == constants.BSX_VAULT_SLUG:
        points_earned = get_points_earned()

        # Incorporate BSX Points:
        # Each point earned can be converted to $0.2.
        # Points earned over the month need to be calculated.
        # Total value of points = Total points earned * $0.2
        # Calculate the value of the points
        points_value = points_earned * 0.2

        # Adjust the total balance (TVL)
        adjusted_tvl = total_balance + points_value

        # Adjust the current PPS
        current_price_per_share = adjusted_tvl / vault_state.total_share

    # Calculate reward APY if this is the Hype vault
    weekly_reward_apy = 0
    monthly_reward_apy = 0
    apy_reward_15day = 0
    apy_reward_45day = 0
    if vault.slug == constants.HYPE_DELTA_NEUTRAL_SLUG:
        weekly_reward_apy, monthly_reward_apy, apy_reward_15day, apy_reward_45day = (
            calculate_reward_apy(vault.id, total_balance)
        )
        logger.info(
            "Reward APY calculated - Weekly: %.2f%%, Monthly: %.2f%%",
            weekly_reward_apy,
            monthly_reward_apy,
        )

    # Calculate Monthly APY
    month_ago_price_per_share = get_before_price_per_shares(session, vault.id, days=30)
    month_ago_datetime = pendulum.instance(month_ago_price_per_share.datetime).in_tz(
        pendulum.UTC
    )

    time_diff = pendulum.now(tz=pendulum.UTC) - month_ago_datetime
    days = min((time_diff).days, 30) if time_diff.days > 0 else time_diff.hours / 24
    monthly_apy = calculate_roi(
        current_price_per_share, month_ago_price_per_share.price_per_share, days=days
    )

    week_ago_price_per_share = get_before_price_per_shares(session, vault.id, days=7)
    week_ago_datetime = pendulum.instance(week_ago_price_per_share.datetime).in_tz(
        pendulum.UTC
    )
    time_diff = pendulum.now(tz=pendulum.UTC) - week_ago_datetime
    days = min(time_diff.days, 7) if time_diff.days > 0 else time_diff.hours / 24
    weekly_apy = calculate_roi(
        current_price_per_share, week_ago_price_per_share.price_per_share, days=days
    )

    apy_ytd = calculate_apy_ytd(vault.id, current_price_per_share)

    # apy 15days
    price_per_share_15_days_ago = get_before_price_per_shares(
        session, vault.id, days=15
    )
    datetime_15_days_ago = pendulum.instance(
        price_per_share_15_days_ago.datetime
    ).in_tz(pendulum.UTC)
    time_diff = pendulum.now(tz=pendulum.UTC) - datetime_15_days_ago
    days_15 = min(time_diff.days, 15) if time_diff.days > 0 else time_diff.hours / 24
    base_apy_15d = calculate_roi(
        current_price_per_share,
        price_per_share_15_days_ago.price_per_share,
        days=days_15,
    )

    # apy 45days
    price_per_share_45_days_ago = get_before_price_per_shares(
        session, vault.id, days=45
    )
    datetime_45_days_ago = pendulum.instance(
        price_per_share_45_days_ago.datetime
    ).in_tz(pendulum.UTC)
    time_diff = pendulum.now(tz=pendulum.UTC) - datetime_45_days_ago
    days_45 = min(time_diff.days, 45) if time_diff.days > 0 else time_diff.hours / 24
    base_apy_45d = calculate_roi(
        current_price_per_share,
        price_per_share_45_days_ago.price_per_share,
        days=days_45,
    )

    performance_history = session.exec(
        select(VaultPerformance).order_by(VaultPerformance.datetime.asc()).limit(1)
    ).first()

    if vault.slug == constants.GOLD_LINK_SLUG:
        current_price = get_price(f"{vault.underlying_asset}USDT")

    benchmark = current_price
    benchmark_percentage = ((benchmark / performance_history.benchmark) - 1) * 100
    # Add reward APY to base APY
    apy_1m = monthly_apy * 100 + monthly_reward_apy
    apy_1w = weekly_apy * 100 + weekly_reward_apy
    apy_15d = base_apy_15d * 100 + apy_reward_15day
    apy_45d = base_apy_45d * 100 + apy_reward_45day
    apy_ytd = apy_ytd * 100

    all_time_high_per_share, sortino, downside, risk_factor = calculate_pps_statistics(
        session, vault.id
    )

    # count all portfolio of vault
    statement = (
        select(func.count())
        .select_from(UserPortfolio)
        .where(UserPortfolio.vault_id == vault.id)
    )
    count = session.scalar(statement)

    # Create a new VaultPerformance object
    performance = VaultPerformance(
        datetime=datetime.now(timezone.utc),
        total_locked_value=total_balance,
        benchmark=benchmark,
        pct_benchmark=benchmark_percentage,
        apy_1m=apy_1m,
        base_monthly_apy=monthly_apy * 100,
        reward_monthly_apy=monthly_reward_apy,
        apy_1w=apy_1w,
        base_weekly_apy=weekly_apy * 100,
        reward_weekly_apy=weekly_reward_apy,
        apy_ytd=apy_ytd,
        vault_id=vault.id,
        risk_factor=risk_factor,
        all_time_high_per_share=all_time_high_per_share,
        total_shares=vault_state.total_share,
        sortino_ratio=sortino,
        downside_risk=downside,
        unique_depositors=count,
        earned_fee=vault_state.total_fee_pool_amount,
        fee_structure=fee_info,
        apy_15d=apy_15d,
        apy_45d=apy_45d,
        base_15d_apy=base_apy_15d,
        base_45d_apy=base_apy_45d,
        reward_15d_apy=apy_reward_15day,
        reward_45d_apy=apy_reward_45day,
    )

    update_price_per_share(vault.id, current_price_per_share)

    return performance


# Main Execution
@click.command()
@click.option("--chain", default="arbitrum_one", help="Blockchain network to use")
def main(chain: str):
    try:
        setup_logging_to_console()
        setup_logging_to_file(
            f"update_delta_neutral_vault_performance_daily_{chain}", logger=logger
        )
        # Parse chain to NetworkChain enum
        network_chain = NetworkChain[chain.lower()]

        # Get the vault from the Vault table with name = "Delta Neutral Vault"
        vaults = session.exec(
            select(Vault)
            .where(
                or_(
                    Vault.strategy_name == constants.DELTA_NEUTRAL_STRATEGY,
                    Vault.slug == constants.GOLD_LINK_SLUG,
                )
            )
            .where(Vault.is_active == True)
            .where(Vault.network_chain == network_chain)
            .where(Vault.category != VaultCategory.real_yield_v2)
            .where(not_(Vault.tags.contains("ended")))
        ).all()

        for vault in vaults:
            logger.info("Updating performance for %s...", vault.name)
            if vault.slug == constants.GOLD_LINK_SLUG:
                vault_contract, _ = get_vault_contract(vault, "goldlink")
            else:
                vault_contract, _ = get_vault_contract(vault)

            new_performance_rec = calculate_performance(
                vault,
                vault_contract,
                vault.owner_wallet_address,
                update_freq=(
                    "daily"
                    if network_chain in {NetworkChain.arbitrum_one, NetworkChain.base}
                    else "weekly"
                ),
            )
            # Add the new performance record to the session and commit
            session.add(new_performance_rec)

            # Update the vault with the new information
            vault.ytd_apy = new_performance_rec.apy_ytd
            vault.monthly_apy = new_performance_rec.apy_1m
            vault.base_monthly_apy = new_performance_rec.base_monthly_apy
            vault.reward_monthly_apy = new_performance_rec.reward_monthly_apy
            vault.weekly_apy = new_performance_rec.apy_1w
            vault.base_weekly_apy = new_performance_rec.base_weekly_apy
            vault.reward_weekly_apy = new_performance_rec.reward_weekly_apy
            vault.apy_15d = new_performance_rec.apy_15d
            vault.apy_45d = new_performance_rec.apy_45d
            vault.next_close_round_date = None
            update_tvl(vault.id, new_performance_rec.total_locked_value)
            logger.info(
                "Vault %s: tvl = %s, apy %s",
                vault.name,
                new_performance_rec.total_locked_value,
                vault.monthly_apy,
            )
            session.commit()
    except Exception as e:
        logger.error(
            "An error occurred while updating delta neutral performance: %s",
            e,
            exc_info=True,
        )
        raise e


if __name__ == "__main__":
    main()
