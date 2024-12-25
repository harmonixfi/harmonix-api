from datetime import datetime, timezone
import json
import logging
import traceback
from typing import Dict, List, Optional
from uuid import UUID
import click
from sqlalchemy import and_, func, text
from sqlmodel import Session, col, select

from core import constants
from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models.reward_distribution_config import RewardDistributionConfig
from models.reward_distribution_history import RewardDistributionHistory
from models.user import User
from models.user_portfolio import PositionStatus, UserPortfolio
from models.user_rewards import UserRewardAudit, UserRewards
from models.vaults import Vault

session = Session(engine)


# # Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rewards_distribution_job_harmonix")
logger.setLevel(logging.INFO)


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

    # Calculate the total reward for distribution based on configuration
    total_reward = reward_config.total_reward * reward_config.distribution_percentage
    logger.info("Total reward for vault %s: %s", vault.name, total_reward)

    # Fetch all active user positions in the vault
    user_positions = get_active_user_positions(vault.id)
    logger.info("Total user positions of vault %s: %s", vault.name, len(user_positions))

    # Calculate the total deposit amount from all active user positions
    total_deposit_amount = sum(user.init_deposit for user in user_positions)
    logger.info(
        "Total deposit amount for vault %s: %s", vault.name, total_deposit_amount
    )

    # Iterate through each user position to distribute rewards
    for portfolio in user_positions:
        user = get_user_by_wallet(portfolio.user_address)
        if not user:
            logger.info("User with wallet address %s not found", portfolio.user_address)
            continue

        # Calculate the percentage of shares for the user based on their deposit
        shares_pct = portfolio.init_deposit / total_deposit_amount
        # Calculate the reward distribution for the user based on their shares percentage
        reward_distribution = shares_pct * total_reward
        # Process the reward distribution for the user
        process_user_reward(
            user,
            vault.id,
            reward_config.start_date,
            reward_distribution,
            current_date,
        )


def process_user_reward(
    user: User, vault_id, start_date, reward_distribution, current_date
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
        logger.info(
            f"Processing rewards for user {user.wallet_address} in vault {vault_id}"
        )

        # Get existing reward record for the user if any
        user_reward = get_user_reward(vault_id, user.wallet_address)
        # Store old reward value for audit purposes
        old_value = user_reward.total_reward if user_reward else 0

        logger.debug(f"Current reward value: {old_value}")

        # Skip if rewards were already processed for this period
        if (
            user_reward
            and user_reward.updated_at.replace(tzinfo=timezone.utc) >= start_date
        ):
            logger.info(
                f"Rewards already processed for user {user.wallet_address} after {start_date}"
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
                    wallet_address=user.wallet_address,
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
            f"Failed to process rewards for user {user.wallet_address}: {str(e)}",
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
    # get all vaults that have VaultCategory = points
    vaults = session.exec(
        select(Vault)
        .where(Vault.slug == constants.HYPE_DELTA_NEUTRAL_SLUG)
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
            update_vault_rewards(current_time=current_date, vault=vault)
        except Exception as e:
            logger.error(
                "An error occurred while calculating rewards for vault %s: %s",
                vault.name,
                e,
                exc_info=True,
            )

    session.commit()


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file(
        app="rewards_distribution_job_harmonix", level=logging.INFO, logger=logger
    )

    cli()
