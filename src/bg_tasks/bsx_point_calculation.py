"""
Implement the logic for calculating the restaking points for a user.
In our system, we have multiple vaults that have VaultCategory = points, we need to calculate points for all the restaking vaults.

1. define function to get earned points from vault address
2. define function to calculate restaking point distributions for each vault to users.

"""

import json
import logging
from typing import Dict, List
from uuid import UUID

import seqlog
from sqlmodel import Session, col, select

from core import constants
from core.config import settings
from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models.point_distribution_history import PointDistributionHistory
from models.user_points import UserPointAudit, UserPoints
from models.user_portfolio import PositionStatus, UserPortfolio
from models.vaults import Vault, VaultCategory
from schemas import EarnedRestakingPoints
from services import bsx_service

session = Session(engine)


# # Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bsx_point_calculation")
logger.setLevel(logging.INFO)


def get_previous_point_distribution(vault_id: UUID, partner_name: str) -> float:
    # get point distribution history for the vault
    prev_point_distribution = session.exec(
        select(PointDistributionHistory)
        .where(PointDistributionHistory.vault_id == vault_id)
        .where(PointDistributionHistory.partner_name == partner_name)
        .order_by(PointDistributionHistory.created_at.desc())
    ).first()

    if prev_point_distribution is not None:
        prev_point = prev_point_distribution.point
    else:
        prev_point = 0

    return prev_point


def distribute_points_to_users(
    vault_id: UUID,
    user_positions: List[UserPortfolio],
    earned_points: float,
    partner_name: str,
):
    """
    Distribute points to users based on their share percentages.
    """
    total_deposit_amount = sum([user.init_deposit for user in user_positions])
    for user in user_positions:
        shares_pct = user.init_deposit / total_deposit_amount

        old_point_value = 0
        user_points = session.exec(
            select(UserPoints)
            .where(UserPoints.wallet_address == user.user_address)
            .where(UserPoints.partner_name == partner_name)
            .where(UserPoints.vault_id == vault_id)
        ).first()

        if user_points:
            old_point_value = user_points.points
            user_points.points += earned_points * shares_pct

        else:
            user_points = UserPoints(
                wallet_address=user.user_address,
                points=earned_points * shares_pct,
                partner_name=partner_name,
                vault_id=vault_id,
            )

        logger.info(
            "User %s, Share pct = %s, Points: %s",
            user.user_address,
            shares_pct,
            user_points.points,
        )
        session.add(user_points)
        session.commit()

        # add UserPointAudit record
        audit = UserPointAudit(
            user_points_id=user_points.id,
            old_value=old_point_value,
            new_value=user_points.points,
        )
        session.add(audit)


def distribute_points(
    vault: Vault,
    partner_name: str,
    user_positions: List[UserPortfolio],
    earned_points_in_period: float,
    total_earned_points: EarnedRestakingPoints,
):

    # calculate user earn points in the period
    distribute_points_to_users(
        vault_id=vault.id,
        user_positions=user_positions,
        earned_points=earned_points_in_period,
        partner_name=partner_name,
    )

    # save the point distribution history
    point_distribution = PointDistributionHistory(
        vault_id=vault.id,
        partner_name=partner_name,
        point=total_earned_points.total_points,
    )
    session.add(point_distribution)


def calculate_point_distributions(vault: Vault):
    user_positions: List[UserPortfolio] = []

    # get all users who have points in the vault
    user_positions = session.exec(
        select(UserPortfolio)
        .where(UserPortfolio.vault_id == vault.id)
        .where(UserPortfolio.status == PositionStatus.ACTIVE)
    ).all()
    logger.info("Total user positions of vault %s: %s", vault.name, len(user_positions))

    partners = [constants.BSX]

    for partner_name in partners:
        # get earned points for the partner
        prev_point = get_previous_point_distribution(vault.id, partner_name)
        logger.info(
            "Vault %s, partner: %s, Previous point distribution: %s",
            vault.name,
            partner_name,
            prev_point,
        )

        total_earned_points = bsx_service.get_points_earned()
        total_earned_points = (
            total_earned_points if total_earned_points >= prev_point else prev_point
        )
        logger.info(
            "Total earned points for partner %s: %s",
            partner_name,
            total_earned_points,
        )

        # the job run every 12 hour, so we need to calculate the earned points in the last 12 hour
        earned_points_in_period = total_earned_points - prev_point
        if earned_points_in_period > 0:
            distribute_points(
                vault,
                partner_name,
                user_positions,
                earned_points_in_period,
                total_earned_points,
            )

    session.commit()


def main():
    # get all vaults that have VaultCategory = points
    vaults = session.exec(
        select(Vault)
        .where(Vault.slug == constants.BSX_VAULT_SLUG)
        .where(Vault.is_active == True)
    ).all()

    for vault in vaults:
        try:
            logger.info(f"Calculating points for vault {vault.name}")
            calculate_point_distributions(vault)
        except Exception as e:
            logger.error(
                "An error occurred while calculating points for vault %s: %s",
                vault.name,
                e,
                exc_info=True,
            )

    session.commit()


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file(
        app="bsx_point_calculation", level=logging.INFO, logger=logger
    )

    main()
