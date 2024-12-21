from datetime import datetime, timezone
import json
import logging
from typing import Dict, List
from uuid import UUID
from sqlmodel import Session, col, select

from core import constants
from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models.reward_distribution_config import RewardDistributionConfig
from models.user import User
from models.user_portfolio import PositionStatus, UserPortfolio
from models.user_rewards import UserRewardAudit, UserRewards
from models.vaults import Vault

session = Session(engine)


# # Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("goldlink_arb_reward_calculation.")
logger.setLevel(logging.INFO)


def get_user_reward(vault_id: UUID, wallet_address: str) -> UserRewards:
    return session.exec(
        select(UserRewards)
        .where(UserRewards.vault_id == vault_id)
        .where(UserRewards.wallet_address == wallet_address)
    ).first()


def get_reward_distribution_config(date: datetime, vault_id: UUID):
    return session.exec(
        select(RewardDistributionConfig)
        .where(RewardDistributionConfig.vault_id == vault_id)
        .where(RewardDistributionConfig.start_date >= date)
        .order_by(RewardDistributionConfig.start_date.desc())
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


def calculate_reward_distributions(vault: Vault):
    current_date = datetime.now(tz=timezone.utc)

    # Fetch the reward configuration for the vault
    reward_config = get_reward_distribution_config(current_date, vault_id=vault.id)
    if not reward_config:
        logger.info(
            "No reward configuration found for vault %s on date %s",
            vault.name,
            current_date,
        )
        return

    total_reward = reward_config.total_reward * reward_config.distribution_percentage
    logger.info("Total reward for vault %s: %s", vault.name, total_reward)

    # Fetch all active user positions in the vault
    user_positions = get_active_user_positions(vault.id)
    logger.info("Total user positions of vault %s: %s", vault.name, len(user_positions))

    total_deposit_amount = sum(user.init_deposit for user in user_positions)
    logger.info(
        "Total deposit amount for vault %s: %s", vault.name, total_deposit_amount
    )

    for portfolio in user_positions:
        user = get_user_by_wallet(portfolio.user_address)
        if not user:
            logger.info("User with wallet address %s not found", portfolio.user_address)
            continue

        shares_pct = portfolio.init_deposit / total_deposit_amount
        reward_distribution = shares_pct * total_reward
        process_user_reward(
            user,
            vault.id,
            reward_config.start_date,
            reward_distribution,
            current_date,
        )


def process_user_reward(user, vault_id, start_date, reward_distribution, current_date):
    user_reward = get_user_reward(vault_id, user.wallet_address)
    old_value = user_reward.total_reward if user_reward else 0

    if user_reward and user_reward.updated_at >= start_date:
        return

    if user_reward:
        user_reward.total_reward += reward_distribution
        user_reward.updated_at = current_date
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

    session.commit()

    create_user_reward_audit(
        user_reward.id, old_value, user_reward.total_reward, current_date
    )


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


def main():
    # get all vaults that have VaultCategory = points
    vaults = session.exec(
        select(Vault)
        .where(Vault.slug == constants.HYPE_DELTA_NEUTRA_SLUG)
        .where(Vault.is_active == True)
    ).all()

    for vault in vaults:
        try:
            logger.info(f"Calculating rewards for vault {vault.name}")
            calculate_reward_distributions(vault)
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

    main()
