from datetime import datetime, timedelta
import logging
import traceback
import uuid
import pandas as pd
from sqlalchemy import func
from sqlmodel import Session, select
from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models import Vault
from models.pps_history import PricePerShareHistory
from models.vault_performance import VaultPerformance

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


def update_apy(vault: Vault, datetime: datetime, apy_15d: float, apy_45d: float):
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
            session.add(result)
        session.commit()


def get_apy_history(vault: Vault) -> pd.DataFrame:
    # Get the latest pps from pps_history table
    pps_history = session.exec(
        select(PricePerShareHistory)
        .where(PricePerShareHistory.vault_id == vault.id)
        .order_by(PricePerShareHistory.datetime.desc())
    ).all()

    # Convert query results into a DataFrame
    df = pd.DataFrame(
        [
            {"datetime": item.datetime, "price_per_share": item.price_per_share}
            for item in pps_history
        ]
    )

    # Convert 'datetime' column to UTC and normalize to the start of the day
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce").dt.normalize()

    df.set_index("datetime", inplace=True)
    # Resample to daily frequency, calculate mean funding rate, and forward-fill missing values
    df_daily = df.resample("D").last()
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
                    apys[current_date] = (
                        calculate_roi(
                            df_daily.loc[
                                current_date, "price_per_share"
                            ],  # current PPS
                            df_daily.loc[past_date, "price_per_share"],  # past PPS
                            days=days_diff,
                        )
                        * 100
                    )  # Convert to percentage
            except Exception as e:
                print(current_date)
                traceback.print_exc()

        # Add the results to df_daily
        df_daily[col_name] = apys

    apy_columns = ["apy_15d", "apy_45d"]
    df_daily[apy_columns] = df_daily[apy_columns].ffill()

    return df_daily


def update_tvl(vault_id: uuid.UUID, current_tvl: float):
    vault = session.exec(select(Vault).where(Vault.id == vault_id)).first()
    if vault:
        vault.tvl = current_tvl
        session.commit()


# Main Execution
def main():
    try:
        logger.info(
            "Starting the process to sync_apy_vault_performance_history for vaults..."
        )
        # Get the vaults from the Vault table
        vaults = session.exec(select(Vault).where(Vault.is_active == True)).all()
        date_now = datetime.now().date()

        for vault in vaults:
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
                        update_apy(
                            vault=vault,
                            datetime=current_date,
                            apy_15d=apy_15d,
                            apy_45d=apy_45d,
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
    setup_logging_to_console()
    setup_logging_to_file("sync_apy_vault_performance_history", logger=logger)
    main()
