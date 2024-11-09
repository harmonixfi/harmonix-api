import json
import logging
from typing import Dict, List
from uuid import UUID
from sqlmodel import Session, col, select

from core import constants
from core.config import settings
from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models.reward_distribution_history import RewardDistributionHistory
from models.user_portfolio import PositionStatus, UserPortfolio
from models.user_rewards import UserRewardAudit, UserRewards
from models.vault_rewards import VaultRewards
from models.vaults import Vault, VaultCategory
from schemas.earned_restaking_rewards import EarnedRestakingRewards
from services.market_data import get_price

session = Session(engine)


# # Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("goldlink_arb_reward_calculation.")
logger.setLevel(logging.INFO)


def get_rewards(vault: Vault, symbol: str = "ARBUSDT") -> EarnedRestakingRewards:
    vault_reward = session.exec(
        select(VaultRewards).where(VaultRewards.vault_id == vault.id)
    ).first()
    return EarnedRestakingRewards(
        wallet_address=vault.contract_address,
        total_rewards=float(vault_reward.earned_rewards),
        partner_name=constants.DELTA_NEUTRAL_STRATEGY,
    )


def get_previous_reward_distribution(vault_id: UUID) -> float:
    # get point distribution history for the vault
    prev_reward_distribution = session.exec(
        select(RewardDistributionHistory)
        .where(RewardDistributionHistory.vault_id == vault_id)
        .order_by(RewardDistributionHistory.created_at.desc())
    ).first()

    if prev_reward_distribution is not None:
        prev_rewards = prev_reward_distribution.total_reward
    else:
        prev_rewards = 0

    return prev_rewards


def distribute_rewards_to_users(
    vault_id: UUID, user_positions: List[UserPortfolio], earned_rewards: float
):
    """
    Distribute rewards to users based on their share percentages.
    """
    total_deposit_amount = sum([user.init_deposit for user in user_positions])
    for user in user_positions:
        shares_pct = user.init_deposit / total_deposit_amount

        old_reward_value = 0
        user_rewards = session.exec(
            select(UserRewards)
            .where(UserRewards.wallet_address == user.user_address)
            .where(UserRewards.vault_id == vault_id)
        ).first()

        if user_rewards:
            old_reward_value = user_rewards.total_reward
            user_rewards.total_reward += earned_rewards * shares_pct

        else:
            user_rewards = UserRewards(
                wallet_address=user.user_address,
                total_reward=earned_rewards * shares_pct,
                partner_name=constants.PARTNER_GODLINK,
                vault_id=vault_id,
            )

        logger.info(
            "User %s, Share pct = %s, total_reward: %s",
            user.user_address,
            shares_pct,
            user_rewards.total_reward,
        )
        session.add(user_rewards)
        session.commit()

        # add UserRewardAudit record
        audit = UserRewardAudit(
            user_points_id=user_rewards.id,
            old_value=old_reward_value,
            new_value=user_rewards.total_reward,
        )
        session.add(audit)


def distribute_rewards(
    vault: Vault,
    user_positions: List[UserPortfolio],
    earned_rewards_in_period: float,
    total_earned_rewards: EarnedRestakingRewards,
):

    # calculate user earn points in the period
    distribute_rewards_to_users(
        vault_id=vault.id,
        user_positions=user_positions,
        earned_rewards=earned_rewards_in_period,
    )

    # save the reward distribution history
    reward_distribution = RewardDistributionHistory(
        vault_id=vault.id,
        partner_name=constants.PARTNER_GODLINK,
        total_reward=total_earned_rewards.total_rewards,
    )
    session.add(reward_distribution)
    session.commit()


def calculate_reward_distributions(vault: Vault):
    user_positions: List[UserPortfolio] = []

    # get all users who have rewards in the vault
    user_positions = session.exec(
        select(UserPortfolio)
        .where(UserPortfolio.vault_id == vault.id)
        .where(UserPortfolio.status == PositionStatus.ACTIVE)
    ).all()
    logger.info("Total user positions of vault %s: %s", vault.name, len(user_positions))

    prev_rewards = get_previous_reward_distribution(vault.id)
    logger.info(
        "Vault %s, Previous reward distribution: %s",
        vault.name,
        prev_rewards,
    )

    rewards = get_rewards(vault)

    rewards.total_rewards = (
        rewards.total_rewards if rewards.total_rewards >= prev_rewards else prev_rewards
    )
    logger.info(
        "Total earned rewards for  %s",
        rewards.total_rewards,
    )

    # the job run every 12 hour, so we need to calculate the earned points in the last 12 hour
    earned_rewards_in_period = rewards.total_rewards - prev_rewards
    if earned_rewards_in_period > 0:
        distribute_rewards(
            vault,
            user_positions,
            earned_rewards_in_period,
            rewards,
        )

        session.commit()


def main():
    # get all vaults that have VaultCategory = points
    vaults = session.exec(
        select(Vault)
        .where(Vault.slug == constants.GOLD_LINK_SLUG)
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
        app="goldlink_arb_reward_calculation", level=logging.INFO, logger=logger
    )

    main()
