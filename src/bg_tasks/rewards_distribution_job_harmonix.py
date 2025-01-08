from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import logging
import traceback
from typing import Dict, List, Optional
from uuid import UUID
import click
import pandas as pd
from sqlalchemy import and_, func, text
from sqlmodel import Session, col, select
from web3 import Web3

from bg_tasks.utils import extract_pendle_event, get_logs_from_tx_hash
from core import constants
from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models.onchain_transaction_history import OnchainTransactionHistory
from models.reward_distribution_config import RewardDistributionConfig
from models.reward_distribution_history import RewardDistributionHistory
from models.user import User
from models.user_portfolio import PositionStatus, UserPortfolio
from models.user_rewards import UserRewardAudit, UserRewards
from models.vaults import Vault
from services.vault_contract_service import VaultContractService

session = Session(engine)

DEPOSIT_TOPIC = "0xf943cf10ef4d1e3239f4716ddecdf546e8ba8ab0e41deafd9a71a99936827e45"
WITHDRAW_TOPIC = "0x29835b361052a697c9f643de976223a59a332b7b4acaefa06267016e3e5d8efa"

# # Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rewards_distribution_job_harmonix")
logger.setLevel(logging.INFO)


def get_amount_from_tx(vault: Vault, input) -> float:
    if input["method_id"] == constants.MethodID.DEPOSIT3.value:
        # Ta muốn filter log deposit
        logs = get_logs_from_tx_hash(vault, input["tx_hash"], topic=DEPOSIT_TOPIC)
        if not logs:
            return 0.0
        event_data = extract_pendle_event(logs[0])
        total_amount = event_data[3]
        return total_amount

    elif input["method_id"] in [
        constants.MethodID.WITHDRAW_PENDLE1.value,
        constants.MethodID.WITHDRAW_PENDLE2.value,
    ]:
        # Tương tự, filter log withdraw
        logs = get_logs_from_tx_hash(vault, input["tx_hash"], topic=WITHDRAW_TOPIC)
        if not logs:
            return 0.0

        event_data = extract_pendle_event(logs[0])
        total_amount = event_data[3]
        return total_amount

    return 0.0  # default


def get_transaction(vault: Vault, end_date: datetime):
    end_date = int(end_date.timestamp())

    # Select specific fields
    query = (
        select(
            OnchainTransactionHistory.tx_hash,
            OnchainTransactionHistory.block_number,
            OnchainTransactionHistory.from_address,
            OnchainTransactionHistory.to_address,
            OnchainTransactionHistory.method_id,
            OnchainTransactionHistory.input,
            OnchainTransactionHistory.value,
            OnchainTransactionHistory.timestamp,
        )
        .where(
            OnchainTransactionHistory.method_id.in_(
                [
                    constants.MethodID.DEPOSIT3.value,
                    constants.MethodID.WITHDRAW_PENDLE1.value,
                    constants.MethodID.WITHDRAW_PENDLE2.value,
                ]
            )
        )
        .where(
            func.lower(OnchainTransactionHistory.to_address)
            == func.lower(vault.contract_address)
        )
        .where(OnchainTransactionHistory.timestamp <= end_date)
    )

    # Execute query and fetch results
    result = session.exec(query).all()

    # Convert to DataFrame
    if result:
        df = pd.DataFrame(
            result,
            columns=[
                "tx_hash",
                "block_number",
                "from_address",
                "to_address",
                "method_id",
                "input",
                "value",
                "timestamp",
            ],
        )
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    else:
        df = pd.DataFrame(
            columns=[
                "tx_hash",
                "block_number",
                "from_address",
                "to_address",
                "method_id",
                "input",
                "value",
                "timestamp",
                "datetime",
            ]
        )  # Empty DataFrame with columns
    df_sorted = df.sort_values(by="datetime")
    df_sorted = df_sorted.reset_index(drop=True)
    return df_sorted


user_balance = defaultdict(float)


def distribute_rewards_daily(
    vault: Vault,
    df_sorted: pd.DataFrame,
    start_date: datetime,
    end_date: datetime,
    total_weekly_reward: float,
) -> pd.DataFrame:
    """
    Calculate daily rewards distribution based on user balances.

    This function processes a DataFrame of sorted transactions to calculate the daily rewards
    distribution for users based on their balances in a specified vault over a defined period.
    It aggregates deposits and withdrawals, computes the daily share of rewards for each user,
    and returns a DataFrame summarizing the total rewards for each user.

    Args:
        vault: Vault object containing contract info.
        df_sorted: DataFrame of sorted transactions, which must include columns for 'from_address',
                   'method_id', and 'datetime'.
        start_date: Start date for the reward period.
        end_date: End date for the reward period.
        total_weekly_reward: Total reward amount for the week to be distributed daily.

    Returns:
        DataFrame with user addresses and their total rewards.

    User Case Flow:
        1. **Initialization**:
            - The function initializes necessary data structures to track user balances,
              balance history, and reward records.

        2. **Input Transactions**:
            - A DataFrame of transactions is provided, which includes deposits and withdrawals
              for users over a specified week.

        3. **Processing Transactions**:
            - The function groups transactions by week and processes them chronologically.
            - For each transaction:
                - If it is a deposit, the user's balance is updated.
                - If it is a withdrawal, the user's balance is set to zero.

        4. **Recording Balances**:
            - After processing each transaction, the function records the user's balance at that
              point in time.

        5. **Calculating Daily Rewards**:
            - The function filters the recorded balances to the specified reward period.
            - It calculates the total balance of all users for each day.
            - For each user, it computes their share of the total balance and the corresponding
              reward based on the daily reward amount.

        6. **Output**:
            - The function returns a DataFrame summarizing the total rewards distributed to each
              user based on their transaction history within the specified date range.

    Example:
        Given a vault and a DataFrame of transactions:

        vault = Vault(...)
        df_sorted = pd.DataFrame({
            'from_address': ['0xabc...', '0xdef...', '0xabc...', '0xdef...'],
            'method_id': [
                constants.MethodID.DEPOSIT3.value,  # User1 deposits
                constants.MethodID.DEPOSIT3.value,  # User2 deposits
                constants.MethodID.WITHDRAW_PENDLE1.value,  # User1 withdraws all
                constants.MethodID.WITHDRAW_PENDLE1.value   # User2 withdraws
            ],
            'datetime': [
                datetime(2023, 10, 1, 12, 0),  # User1 deposit
                datetime(2023, 10, 1, 12, 0),  # User2 deposit
                datetime(2023, 10, 2, 12, 0),  # User1 withdraws all
                datetime(2023, 10, 2, 12, 0)   # User2 withdraws
            ],
            'value': [100, 100, 100, 0]  # Assuming value is the amount involved in the transaction
        })
        start_date = datetime(2023, 10, 1)
        end_date = datetime(2023, 10, 7)
        total_weekly_reward = 100.0  # Total rewards to be distributed for the week

        rewards_df = distribute_rewards_daily(vault, df_sorted, start_date, end_date, total_weekly_reward)
        print(rewards_df)

        In this scenario:
        - User1 and User2 both start with a balance of 100.
        - The total weekly reward is 100, so each day, 14.29 (100/7) will be distributed.
        - On day 2, User1 withdraws all their balance, leaving User2 with 100% of the balance.
        - Therefore, User2 will receive the full daily reward of 14.29 for that day.

        The output DataFrame will show the total rewards distributed to each user based on their transaction history within the specified date range.
    """
    logger.info(f"Starting reward distribution for {len(df_sorted)} transactions")

    # Initialize tracking structures
    user_balance = defaultdict(float)
    balance_history = []
    reward_records = []
    daily_reward = total_weekly_reward / 7

    # Group transactions by week (ending Wednesday)
    weekly_groups = df_sorted.groupby(pd.Grouper(key="datetime", freq="W-WED"))

    # Process transactions week by week
    for week_date, week_transactions in weekly_groups:
        if week_transactions.empty:
            continue

        logger.info(
            f"Processing week: {week_date.date()} - Transactions: {len(week_transactions)}"
        )

        # Process transactions chronologically within each week
        for _, tx in week_transactions.sort_values("datetime").iterrows():
            wallet = tx["from_address"]
            if not wallet:
                logger.warning(
                    f"Skipping transaction - No wallet address: {tx['tx_hash']}"
                )
                continue

            # Handle deposits
            if tx["method_id"] == constants.MethodID.DEPOSIT3.value:
                deposit_amount = get_amount_from_tx(vault, tx)
                user_balance[wallet] += deposit_amount

                logger.debug(
                    f"Deposit: {wallet[:8]}... "
                    f"Amount: {deposit_amount:.6f} "
                    f"New Balance: {user_balance[wallet]:.6f}"
                )

            # Handle withdrawals
            elif tx["method_id"] in {
                constants.MethodID.WITHDRAW_PENDLE1.value,
                constants.MethodID.WITHDRAW_PENDLE2.value,
            }:
                user_balance[wallet] = 0.0
                logger.debug(f"Withdraw: {wallet[:8]}... Balance set to 0")

            # Record balance snapshot
            balance_history.append(
                {
                    "wallet": wallet,
                    "balance": user_balance[wallet],
                    "datetime": tx["datetime"],
                }
            )

    # Filter balance history to reward period
    df_balances = pd.DataFrame(balance_history)
    df_period = df_balances[
        (df_balances["datetime"] >= start_date) & (df_balances["datetime"] <= end_date)
    ]

    for day, day_group in df_period.groupby("datetime"):
        # Calculate rewards per day
        total_balance = day_group["balance"].sum()
        if total_balance > 0:
            for _, position in day_group.iterrows():
                if position["balance"] <= 0:
                    continue

                # Calculate user's share and reward
                user_share = position["balance"] / total_balance
                user_reward = user_share * daily_reward

                reward_records.append(
                    {
                        "date": day,
                        "user_address": position["wallet"],
                        "balance": position["balance"],
                        "reward": user_reward,
                    }
                )

                logger.debug(
                    f"Date: {day.date()} "
                    f"User: {position['wallet'][:8]}... "
                    f"Balance: {position['balance']:.6f} "
                    f"Share: {user_share:.4%} "
                    f"Reward: {user_reward:.6f}"
                )
        else:
            logger.info("No rewards distributed - Total balance is 0")

    # Aggregate total rewards per user
    df_rewards = pd.DataFrame(reward_records)
    if df_rewards.empty:
        return pd.DataFrame(columns=["user_address", "total_reward"])

    return df_rewards.groupby("user_address", as_index=False).agg(
        total_reward=("reward", "sum")
    )[["user_address", "total_reward"]]


def get_user_reward(vault_id: UUID, wallet_address: str) -> UserRewards:
    return session.exec(
        select(UserRewards)
        .where(UserRewards.vault_id == vault_id)
        .where(UserRewards.wallet_address == wallet_address)
    ).first()


def get_reward_distribution_config(
    date: datetime, vault_id: UUID, week: Optional[int] = None
) -> RewardDistributionConfig:
    # This function retrieves the reward distribution configuration for a given vault, date, and optional week.
    # Parameters:
    # - date: The date for which the configuration is needed.
    # - vault_id: The unique identifier of the vault.
    # - week: An optional parameter specifying the week number for which the configuration is needed.
    #
    # If a week is specified, it directly fetches the configuration for that week.
    # Otherwise, it filters the configurations based on the vault ID and the date range within which the configuration is active.
    # The date range is defined as the start date of the configuration to the start date plus 7 days.
    # The configurations are ordered by their start date, and the most recent one is returned.

    if week:
        return session.exec(
            select(RewardDistributionConfig)
            .where(RewardDistributionConfig.vault_id == vault_id)
            .where(RewardDistributionConfig.week == week)
        ).first()

    return session.exec(
        select(RewardDistributionConfig)
        .where(RewardDistributionConfig.vault_id == vault_id)
        .where(
            and_(
                RewardDistributionConfig.start_date + text("interval '7 days'") > date,
                RewardDistributionConfig.start_date <= date,
            )
        )
        .order_by(RewardDistributionConfig.start_date)
    ).first()


def get_active_user_positions(vault_id: UUID):
    return session.exec(
        select(UserPortfolio)
        .where(UserPortfolio.vault_id == vault_id)
        .where(UserPortfolio.status == PositionStatus.ACTIVE)
    ).all()


def get_user_by_wallet(wallet_address: str):
    return session.exec(
        select(User).where(User.wallet_address == wallet_address)
    ).first()


def calculate_reward_distributions(
    vault: Vault, current_date: datetime, week: Optional[int] = None
):
    # Fetch the reward configuration for the vault
    reward_config = get_reward_distribution_config(current_date, vault_id=vault.id)
    if not reward_config:
        logger.info(
            "No reward configuration found for vault %s on date %s",
            vault.name,
            current_date,
        )
        return
    start_date = reward_config.start_date
    end_date = reward_config.start_date + timedelta(days=7)
    df_sorted = get_transaction(vault, end_date)
    total_weekly_reward = (
        reward_config.total_reward * reward_config.distribution_percentage
    )

    reward_users = distribute_rewards_daily(
        vault=vault,
        df_sorted=df_sorted,
        start_date=start_date,
        end_date=end_date,
        total_weekly_reward=total_weekly_reward,
    )

    for _, row in reward_users.iterrows():
        user_address = row["user_address"]
        total_reward = row["total_reward"]
        logger.info(f"User {user_address} reward: {total_reward}")

        # Process the reward distribution for the user
        process_user_reward(
            user_address,
            vault.id,
            reward_config.start_date,
            total_reward,
            current_date,
        )


def process_user_reward(
    wallet_address: str, vault_id, start_date, reward_distribution, current_date
):
    """Process and update rewards for a specific user in the Harmonix vault.

    Args:
        user: User object containing wallet address and other user details
        vault_id: ID of the vault for which rewards are being processed
        start_date: Starting date for reward calculation period
        reward_distribution: Amount of rewards to be distributed
        current_date: Current timestamp for updating records

    Flow:
        1. Get existing user reward record if any
        2. Check if rewards were already processed for this period
        3. Update or create new reward record
        4. Create audit trail for reward changes
    """
    try:
        logger.info(f"Processing rewards for user {wallet_address} in vault {vault_id}")

        # Get existing reward record for the user if any
        user_reward = get_user_reward(vault_id, wallet_address)
        # Store old reward value for audit purposes
        old_value = user_reward.total_reward if user_reward else 0

        logger.debug(f"Current reward value: {old_value}")

        # Skip if rewards were already processed for this period
        if (
            user_reward
            and user_reward.updated_at.replace(tzinfo=timezone.utc) >= start_date
        ):
            logger.info(
                f"Rewards already processed for user {wallet_address} after {start_date}"
            )
            return

        try:
            # Update existing reward record
            if user_reward:
                user_reward.total_reward += reward_distribution
                user_reward.updated_at = current_date
            # Create new reward record
            else:
                user_reward = UserRewards(
                    vault_id=vault_id,
                    wallet_address=wallet_address,
                    total_reward=reward_distribution,
                    created_at=current_date,
                    updated_at=current_date,
                    partner_name=constants.HARMONIX,
                )
                session.add(user_reward)

            # Commit changes to database
            session.commit()

            create_user_reward_audit(
                user_reward.id, old_value, user_reward.total_reward, current_date
            )

        except Exception as db_error:
            logger.error(
                f"Database operation failed while processing rewards: {str(db_error)}",
                exc_info=True,
            )
            session.rollback()
            raise

    except Exception as e:
        logger.error(
            f"Failed to process rewards for user {wallet_address}: {str(e)}",
            exc_info=True,
        )
        if session:
            session.rollback()
        raise


def create_user_reward_audit(
    user_reward_id, old_value: float, new_value: float, current_date: datetime
):
    user_reward_audit = UserRewardAudit(
        user_points_id=user_reward_id,
        old_value=old_value,
        new_value=new_value,
        created_at=current_date,
    )
    session.add(user_reward_audit)
    session.commit()


def update_vault_rewards(current_time, vault: Vault):
    """
    Updates the rewards distribution history for a given vault.

    This function calculates the total rewards earned by a vault from the Harmonix partner
    and records this information in the rewards distribution history. It logs the total
    rewards and updates the database with the new history entry.

    Parameters:
    - current_time: The current timestamp to be recorded in the history.
    - vault: The Vault object for which the rewards distribution history is being updated.

    Logs:
    - Information about the total rewards earned by the vault.
    - Confirmation of the rewards distribution history update.
    - Errors encountered during the process.

    Raises:
    - Exception: If any error occurs during the database operations, it logs the error
      and raises the exception.
    """
    try:
        # get all earned points for the vault
        total_rewards_query = (
            select(func.sum(UserRewards.total_reward))
            .where(UserRewards.vault_id == vault.id)
            .where(UserRewards.partner_name == constants.HARMONIX)
        )
        total_rewards = session.exec(total_rewards_query).one()
        logger.info(
            f"Vault {vault.name} has earned {total_rewards_query} points from Harmonix."
        )
        # insert rewards distribution history
        reward_distribution_history = RewardDistributionHistory(
            vault_id=vault.id,
            partner_name=constants.HARMONIX,
            total_reward=total_rewards,
            created_at=current_time,
        )
        session.add(reward_distribution_history)
        session.commit()
        logger.info("Rewards distribution history updated.")
    except Exception as e:
        logger.error(
            f"An error occurred while updating rewards distribution history for vault {vault.name}: {e}",
            exc_info=True,
        )
        logger.error(traceback.format_exc())


@click.group(invoke_without_command=True)
@click.option(
    "--week",
    type=str,
    default=None,
    help="Optional week parameter to specify the week number for rewards distribution (e.g., 1 for the first week of the year)",
)
@click.pass_context
def cli(ctx, week: Optional[str] = None):
    """Rewards Distribution Job CLI."""
    if ctx.invoked_subcommand is None:
        main(week)


@cli.command()
@click.option(
    "--week",
    type=str,
    default=None,
    help="Optional week parameter to specify the week for rewards distribution (e.g., 2024-W01)",
)
def main(week: Optional[str] = None):
    # apply only Pendle Protected Yield Vault 26jun2025
    vaults = session.exec(
        select(Vault)
        .where(Vault.slug == constants.PENDLE_RSETH_26JUN25_SLUG)
        .where(Vault.is_active == True)
    ).all()

    week_number = int(week) if week else None
    # Get the current date in UTC timezone
    current_date = datetime.now(tz=timezone.utc)
    logger.info(f"Calculating rewards {week_number}")
    for vault in vaults:
        try:
            logger.info(f"Calculating rewards for vault {vault.name}")
            calculate_reward_distributions(vault, current_date, week=week_number)

        except Exception as e:
            logger.error(
                "An error occurred while calculating rewards for vault %s: %s",
                vault.name,
                e,
                exc_info=True,
            )

    # session.commit()


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file(
        app="rewards_distribution_job_harmonix", level=logging.INFO, logger=logger
    )

    cli()
