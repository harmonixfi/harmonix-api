from datetime import datetime, timedelta
import logging
import traceback
import uuid
import pandas as pd
import pendulum
from sqlalchemy import and_, func
from sqlmodel import Session, select
from bg_tasks.update_delta_neutral_vault_performance_daily import calculate_reward_apy
from core import constants
from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models import Vault
from models.pps_history import PricePerShareHistory
from models.vault_performance import VaultPerformance
from services import pendle_service

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sync_apy_vault_performance_history")

session = Session(engine)


def calculate_roi(current_value: float, previous_value: float, days: float) -> float:
    """Calculate annualized ROI"""
    if previous_value == 0:
        return 0
    roi = (current_value / previous_value) - 1
    annualized_roi = (1 + roi) ** (365 / days) - 1
    return annualized_roi


def get_date_init_vault(vault: Vault) -> datetime:
    statement = (
        select(VaultPerformance.datetime)
        .where(VaultPerformance.vault_id == vault.id)
        .order_by(VaultPerformance.datetime)
    )
    result = session.exec(statement).first()
    return result.date()


def update_apy(
    vault: Vault,
    datetime: datetime,
    apy_15d: float,
    apy_45d: float,
    reward_15d_apy: float,
    reward_45d_apy: float,
):
    statement = (
        select(VaultPerformance)
        .where(func.date(VaultPerformance.datetime) == datetime)
        .where(VaultPerformance.vault_id == vault.id)
    )
    results = session.exec(statement).all()
    if results:
        for result in results:
            result.apy_15d = apy_15d
            result.apy_45d = apy_45d
            result.base_15d_apy = apy_15d - reward_15d_apy
            result.base_45d_apy = apy_45d - reward_45d_apy
            result.reward_15d_apy = reward_15d_apy
            result.reward_45d_apy = reward_45d_apy
            session.add(result)
        session.commit()


def get_apy_history(vault: Vault) -> pd.DataFrame:
    # Get the price per share and total locked value history by joining tables
    combined_history = session.exec(
        select(
            PricePerShareHistory.datetime,
            PricePerShareHistory.price_per_share,
            VaultPerformance.total_locked_value,
        )
        .join(
            VaultPerformance,
            (PricePerShareHistory.vault_id == VaultPerformance.vault_id)
            & (
                func.date(PricePerShareHistory.datetime)
                == func.date(VaultPerformance.datetime)
            ),
        )
        .where(PricePerShareHistory.vault_id == vault.id)
        .order_by(PricePerShareHistory.datetime.asc())
    ).all()

    # Convert query results into a DataFrame
    df = pd.DataFrame(
        [
            {
                "datetime": item.datetime,
                "price_per_share": item.price_per_share,
                "total_locked_value": item.total_locked_value,
            }
            for item in combined_history
        ]
    )

    # Convert 'datetime' column to UTC and normalize to the start of the day
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce").dt.normalize()

    df.set_index("datetime", inplace=True)
    # Resample to daily frequency, calculate mean funding rate, and forward-fill missing values
    df_daily = df.resample("D").last()
    df_daily = df_daily.ffill()
    df_daily.index = pd.to_datetime(df_daily.index)

    # Calculate APY for different windows
    for window_days in [15, 45]:
        col_name = f"apy_{window_days}d"

        # Create empty series for results
        apys = pd.Series(index=df_daily.index)

        # Calculate APY for each date
        for current_date in df_daily.index:
            try:
                # Get the date N days ago
                past_date = max(
                    df_daily.index[0],  # first available date
                    current_date - pd.Timedelta(days=window_days),  # N days ago
                )

                # Calculate actual number of days between points
                days_diff = min(window_days, (current_date - df_daily.index[0]).days)

                # If days_diff is 0, set APY to 0
                if days_diff == 0:
                    apys[current_date] = 0
                else:
                    # Calculate APY
                    calculated_apy = (
                        calculate_roi(
                            df_daily.loc[
                                current_date, "price_per_share"
                            ],  # current PPS
                            df_daily.loc[past_date, "price_per_share"],  # past PPS
                            days=days_diff,
                        )
                        * 100
                    )  # Convert to percentage

                    logger.info(
                        "Calculating %d-day APY - Date: %s, Past date: %s, APY: %.2f%%",
                        window_days,
                        current_date.strftime("%Y-%m-%d"),
                        past_date.strftime("%Y-%m-%d"),
                        calculated_apy,
                    )

                    apys[current_date] = calculated_apy
            except Exception as e:
                print(current_date)
                traceback.print_exc()

        # Add the results to df_daily
        df_daily[col_name] = apys
        df_daily[f"base_{window_days}d_apy"] = apys

    if vault.strategy_name == constants.PENDLE_HEDGING_STRATEGY:
        pendle_data = pendle_service.get_market(
            constants.CHAIN_IDS["CHAIN_ARBITRUM"], vault.pt_address
        )
        if pendle_data:
            pendle_market_data = pendle_data[0]
        if pendle_market_data:
            pendle_fixed_yield = (pendle_market_data.implied_apy / 2) * 100
            df_daily.loc[current_date, "apy_15d"] += pendle_fixed_yield
            df_daily.loc[current_date, "apy_45d"] += pendle_fixed_yield

    # Add reward APY if this is the Pendle RSeth vault
    if vault.slug == constants.PENDLE_RSETH_26JUN25_SLUG:
        # Create columns for reward APYs
        reward_columns = {
            7: "reward_weekly_apy",
            15: "reward_15d_apy",
            30: "reward_monthly_apy",
            45: "reward_45d_apy",
        }

        for current_date in df_daily.index:
            # Get TVL for the date
            tvl = (
                df_daily.loc[current_date, "total_locked_value"]
                if "total_locked_value" in df_daily.columns
                else 0
            )

            # Calculate reward APYs for this date
            reward_weekly_apy, reward_monthly_apy, reward_apy_15d, reward_apy_45d = (
                calculate_reward_apy(
                    vault_id=vault.id,
                    total_tvl=tvl,
                    current_date=pendulum.instance(current_date),
                )
            )

            # Add reward APYs to DataFrame
            df_daily.loc[current_date, reward_columns[7]] = reward_weekly_apy
            df_daily.loc[current_date, reward_columns[15]] = reward_apy_15d
            df_daily.loc[current_date, reward_columns[30]] = reward_monthly_apy
            df_daily.loc[current_date, reward_columns[45]] = reward_apy_45d

            # Add reward APYs to base APYs
            df_daily.loc[current_date, "apy_15d"] += reward_apy_15d
            df_daily.loc[current_date, "apy_45d"] += reward_apy_45d

    apy_columns = ["apy_15d", "apy_45d", "base_15d_apy", "base_45d_apy"]
    df_daily[apy_columns] = df_daily[apy_columns].ffill()

    return df_daily


def update_tvl(vault_id: uuid.UUID, current_tvl: float):
    vault = session.exec(select(Vault).where(Vault.id == vault_id)).first()
    if vault:
        vault.tvl = current_tvl
        session.commit()


def update_ended_vault_apy(vault: Vault):
    """
    Update APY values for ended vaults by copying weekly/monthly APYs to 15d/45d APYs
    and setting all reward APYs to 0.
    """
    if "ended" not in vault.get_tags():
        return

    logger.info(f"Updating ended vault APY for vault: {vault.name}")

    # Update vault's APY fields
    vault.apy_15d = vault.weekly_apy
    vault.apy_45d = vault.monthly_apy
    session.add(vault)

    statement = select(VaultPerformance).where(VaultPerformance.vault_id == vault.id)
    performances = session.exec(statement).all()

    for perf in performances:
        # Copy weekly APY to 15d APY
        perf.apy_15d = perf.apy_1w
        perf.base_15d_apy = (
            perf.base_weekly_apy if perf.base_weekly_apy else perf.apy_1w
        )
        perf.reward_15d_apy = 0

        # Copy monthly APY to 45d APY
        perf.apy_45d = perf.apy_1m
        perf.base_45d_apy = (
            perf.base_monthly_apy if perf.base_monthly_apy else perf.apy_1m
        )
        perf.reward_45d_apy = 0

        session.add(perf)

    session.commit()
    logger.info(f"Successfully updated ended vault APY for vault: {vault.name}")


# Main Execution
def main():
    try:
        logger.info(
            "Starting the process to sync_apy_vault_performance_history for vaults..."
        )
        # Get the vaults from the Vault table
        vaults = session.exec(select(Vault).where(Vault.is_active == True)).all()
        # vaults = session.exec(
        #     select(Vault).where(
        #         and_(
        #             Vault.is_active == True,
        #             Vault.tags.contains("ended")
        #         )
        #     )
        # ).all()
        date_now = datetime.now().date()

        for vault in vaults:
            if 'ended' in vault.get_tags():
                update_ended_vault_apy(vault)
                continue

            df_daily = get_apy_history(vault=vault)
            start_date = get_date_init_vault(vault=vault)
            current_date = start_date
            while current_date <= date_now:
                try:
                    result = df_daily.loc[
                        df_daily.index.strftime("%Y-%m-%d")
                        == current_date.strftime("%Y-%m-%d")
                    ]
                    if not result.empty:
                        if isinstance(result, pd.DataFrame):
                            result = result.iloc[0]
                    else:
                        logger.warning(
                            f"Missing APY values for date: {current_date}. Vault: {vault.name}"
                        )

                        # Skip the rest of the loop for this date
                        current_date += pd.Timedelta(days=1)
                        continue

                    if pd.isnull(result["apy_15d"]) or pd.isnull(result["apy_45d"]):
                        logger.warning(
                            f"Missing APY values for date: {current_date}. APY 15d: {result['apy_15d']}, APY 45d: {result['apy_45d']}"
                        )

                    else:
                        apy_15d = result["apy_15d"]
                        apy_45d = result["apy_45d"]
                        reward_15d_apy = result.get("reward_15d_apy", 0)
                        reward_45d_apy = result.get("reward_45d_apy", 0)

                        update_apy(
                            vault=vault,
                            datetime=current_date,
                            apy_15d=apy_15d,
                            apy_45d=apy_45d,
                            reward_15d_apy=reward_15d_apy,
                            reward_45d_apy=reward_45d_apy,
                        )
                        logger.info(
                            f"Successfully updated APY data for {current_date}: APY 15 days = {apy_15d}, APY 45 days = {apy_45d}"
                        )

                except Exception as e:
                    logger.error(
                        f"Error occurred while processing date {current_date}: %s",
                        e,
                        exc_info=True,
                    )
                current_date += timedelta(days=1)

    except Exception as e:
        print(traceback.print_exc())
        logger.error(
            "An error occurred while updating sync_apy_vault_performance_history: %s",
            e,
            exc_info=True,
        )


if __name__ == "__main__":
    setup_logging_to_file("sync_apy_vault_performance_history", logger=logger)
    main()
