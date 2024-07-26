import logging
from datetime import datetime, timedelta, timezone
import traceback
import uuid
from sqlmodel import Session, select
from log import setup_logging_to_file
from models.point_distribution_history import PointDistributionHistory
from models.points_multiplier_config import PointsMultiplierConfig
from models.referral_points import ReferralPoints
from models.referral_points_history import ReferralPointsHistory
from models.referrals import Referral
from models.reward_session_config import RewardSessionConfig
from models.reward_sessions import RewardSessions
from models.user import User
from models.user_points import UserPoints
from models.user_points_history import UserPointsHistory
from models.user_portfolio import PositionStatus, UserPortfolio
from models.vaults import Vault
from core.db import engine
from core import constants
from sqlmodel import Session, select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

session = Session(engine)

POINT_PER_DOLLAR = 1000


def harmonix_distribute_points(current_time):
    try:
        logger.info("Starting Harmonix points distribution job at %s", current_time)

        # Get reward session with end_date = null, and partner_name = Harmonix
        reward_session_query = (
            select(RewardSessions)
            .where(RewardSessions.partner_name == constants.HARMONIX)
            .where(RewardSessions.end_date == None)
        )
        reward_session = session.exec(reward_session_query).first()
        if not reward_session:
            logger.info("No active reward session found for Harmonix.")
            return

        logger.info("Active reward session found: %s", reward_session.session_name)

        # Get reward session config
        reward_session_config_query = select(RewardSessionConfig).where(
            RewardSessionConfig.session_id == reward_session.session_id
        )
        reward_session_config = session.exec(reward_session_config_query).first()
        if not reward_session_config:
            logger.info("No reward session config found for Harmonix.")
            return

        logger.info("Reward session config loaded")

        session_start_date = reward_session.start_date.replace(tzinfo=timezone.utc)
        session_end_date = (
            session_start_date
            + timedelta(minutes=reward_session_config.duration_in_minutes)
        ).replace(tzinfo=timezone.utc)
        if session_end_date < current_time:
            reward_session.end_date = current_time
            session.commit()
            logger.info("%s has ended.", reward_session.session_name)
            return

        if current_time < session_start_date:
            logger.info("%s has not started yet.", reward_session.session_name)
            return

        total_points_distributed = 0
        if (
            reward_session.points_distributed is not None
            and reward_session.points_distributed > 0
        ):
            total_points_distributed = reward_session.points_distributed
        else:
            session_points_query = (
                select(UserPoints)
                .where(UserPoints.partner_name == constants.HARMONIX)
                .where(UserPoints.created_at >= session_start_date)
            )
            total_points_distributed = sum(
                [
                    user_points.points
                    for user_points in session.exec(session_points_query).all()
                ]
            )

        if total_points_distributed >= reward_session_config.max_points:
            logger.info(
                "Maximum points for %s have been distributed.",
                reward_session.session_name,
            )
            return

        # Get all points multiplier config and make a dictionary with vault_id as key
        multiplier_config_query = select(PointsMultiplierConfig)
        multiplier_configs = session.exec(multiplier_config_query).all()
        multiplier_config_dict = {
            mc.vault_id: mc.multiplier for mc in multiplier_configs
        }
        logger.info("Multiplier config loaded: %s", multiplier_config_dict)

        # Fetch active user portfolios
        active_portfolios_query = select(UserPortfolio).where(
            UserPortfolio.status == PositionStatus.ACTIVE
        )
        active_portfolios = session.exec(active_portfolios_query).all()
        active_portfolios.sort(key=lambda x: x.trade_start_date)
        logger.info("Active portfolios retrieved: %d", len(active_portfolios))

        for portfolio in active_portfolios:
            if portfolio.vault_id not in multiplier_config_dict:
                continue

            vault_multiplier = multiplier_config_dict[portfolio.vault_id]
            referrer_multiplier = 1
            logger.debug("Processing portfolio: %s", portfolio)

            # Get user by wallet address
            user_query = select(User).where(
                User.wallet_address == portfolio.user_address
            )
            user = session.exec(user_query).first()
            if not user:
                logger.debug("User not found for address: %s", portfolio.user_address)
                continue

            # Get referral by referee_id
            referral_query = select(Referral).where(Referral.referee_id == user.user_id)
            referral = session.exec(referral_query).first()
            if referral:
                # Get referrer user by user_id
                referrer_query = select(User).where(
                    User.user_id == referral.referrer_id
                )
                referrer = session.exec(referrer_query).first()
                if referrer:
                    if (
                        referrer.tier == constants.UserTier.KOL.value
                        or referrer.tier == constants.UserTier.PARTNER.value
                    ):
                        if (
                            current_time
                            - referrer.created_at.replace(tzinfo=timezone.utc)
                        ).days < 14:
                            referrer_multiplier = 2

            # Get user points distributed for the user by wallet_address
            user_points_query = (
                select(UserPoints)
                .where(UserPoints.wallet_address == portfolio.user_address)
                .where(UserPoints.partner_name == constants.HARMONIX)
                .where(UserPoints.session_id == reward_session.session_id)
                .where(UserPoints.vault_id == portfolio.vault_id)
            )
            user_points = session.exec(user_points_query).first()

            if not user_points:
                # Calculate points to be distributed
                duration_hours = (
                    current_time
                    - max(
                        session_start_date.replace(tzinfo=timezone.utc),
                        portfolio.trade_start_date.replace(tzinfo=timezone.utc),
                    )
                ).total_seconds() / 3600
                points = (
                    (portfolio.total_balance / POINT_PER_DOLLAR)
                    * duration_hours
                    * vault_multiplier
                    * referrer_multiplier
                )

                # Check if the total points exceed the maximum allowed
                if total_points_distributed + points > reward_session_config.max_points:
                    points = reward_session_config.max_points - total_points_distributed

                # Create UserPoints entry
                user_points = UserPoints(
                    vault_id=portfolio.vault_id,
                    wallet_address=portfolio.user_address,
                    points=points,
                    partner_name=constants.HARMONIX,
                    session_id=reward_session.session_id,
                    created_at=current_time,
                )
                session.add(user_points)
                user_points_history = UserPointsHistory(
                    user_points_id=user_points.id,
                    point=points,
                    created_at=current_time,
                    updated_at=current_time,
                )
                session.add(user_points_history)
                session.commit()

                total_points_distributed += points
                logger.info(
                    "Distributed %f points to user %s", points, portfolio.user_address
                )

                if total_points_distributed >= reward_session_config.max_points:
                    reward_session.end_date = current_time
                    session.commit()
                    logger.info("Maximum points reached. Ending session.")
                    break
            else:
                # Get last user points history
                user_points_history_query = (
                    select(UserPointsHistory)
                    .where(UserPointsHistory.user_points_id == user_points.id)
                    .order_by(UserPointsHistory.created_at.desc())
                )
                user_points_history = session.exec(user_points_history_query).first()

                # Calculate points to be distributed
                duration_hours = (
                    current_time
                    - user_points_history.created_at.replace(tzinfo=timezone.utc)
                ).total_seconds() / 3600
                points = (
                    (portfolio.total_balance / POINT_PER_DOLLAR)
                    * duration_hours
                    * vault_multiplier
                    * referrer_multiplier
                )

                # Check if the total points exceed the maximum allowed
                if total_points_distributed + points > reward_session_config.max_points:
                    points = reward_session_config.max_points - total_points_distributed

                # Update UserPoints entry
                user_points.points += points
                user_points.updated_at = current_time
                user_points_history = UserPointsHistory(
                    user_points_id=user_points.id,
                    point=points,
                    created_at=current_time,
                    updated_at=current_time,
                )
                session.add(user_points_history)
                session.commit()

                total_points_distributed += points
                logger.info(
                    "Updated %f points for user %s", points, portfolio.user_address
                )

                if total_points_distributed >= reward_session_config.max_points:
                    reward_session.end_date = current_time
                    session.commit()
                    logger.info("Maximum points reached. Ending session.")
                    break

        reward_session.points_distributed = total_points_distributed
        reward_session.update_date = current_time
        session.commit()
        logger.info(
            "Points distribution job completed with %f points distributed.",
            total_points_distributed,
        )

        update_referral_points(
            current_time,
            reward_session,
            reward_session_config,
            total_points_distributed,
        )
    except Exception as e:
        logger.error(
            "An error occurred during Harmonix points distribution: %s",
            e,
            exc_info=True,
        )
        logger.error(traceback.format_exc())


def update_referral_points(
    current_time, reward_session, reward_session_config, total_points_distributed
):
    try:
        logger.info("Starting referral points update at %s", current_time)

        referrals_query = select(Referral).order_by(Referral.referrer_id)
        referrals = session.exec(referrals_query).all()
        referrals_copy = referrals.copy()
        unique_referrers = []
        for referral in referrals_copy:
            if referral.referrer_id not in unique_referrers:
                unique_referrers.append(referral.referrer_id)

        for referrer_id in unique_referrers:
            referrer_referrals = list(
                filter(lambda referral: referral.referrer_id == referrer_id, referrals)
            )
            referral_points_query = (
                select(ReferralPoints)
                .where(ReferralPoints.user_id == referrer_id)
                .where(ReferralPoints.session_id == reward_session.session_id)
            )
            user_referral_points = session.exec(referral_points_query).first()
            if user_referral_points:
                referral_points = 0
                for referral in referrer_referrals:
                    user_points = get_user_points_by_referee_id(
                        referral, reward_session, session
                    )
                    if not user_points:
                        continue
                    # Get points from points_history
                    user_points_history_query = (
                        select(UserPointsHistory)
                        .where(UserPointsHistory.user_points_id == user_points.id)
                        .order_by(UserPointsHistory.created_at.desc())
                    )
                    user_points_history = session.exec(
                        user_points_history_query
                    ).first()
                    referral_points += user_points_history.point
                referral_points = adjust_referral_points_within_bounds(
                    reward_session_config, total_points_distributed, referral_points
                )
                user_referral_points.points += referral_points
                user_referral_points.updated_at = current_time
                referral_points_history = ReferralPointsHistory(
                    referral_points_id=user_referral_points.id,
                    point=referral_points,
                    created_at=current_time,
                )
                session.add(referral_points_history)
                session.commit()
                total_points_distributed += referral_points
                logger.info(
                    "Updated %f referral points for referrer %s",
                    referral_points,
                    referrer_id,
                )

                if total_points_distributed >= reward_session_config.max_points:
                    reward_session.end_date = current_time
                    session.commit()
                    break
            else:
                referral_points = 0
                for referral in referrer_referrals:
                    user_points = get_user_points_by_referee_id(
                        referral, reward_session, session
                    )
                    if not user_points:
                        continue
                    referral_points += user_points.points
                referral_points = adjust_referral_points_within_bounds(
                    reward_session_config, total_points_distributed, referral_points
                )

                user_referral_points = ReferralPoints(
                    id=uuid.uuid4(),
                    user_id=referrer_id,
                    points=referral_points,
                    created_at=current_time,
                    updated_at=current_time,
                    session_id=reward_session.session_id,
                )
                session.add(user_referral_points)
                referral_points_history = ReferralPointsHistory(
                    referral_points_id=user_referral_points.id,
                    point=referral_points,
                    created_at=current_time,
                )
                session.add(referral_points_history)
                session.commit()
                total_points_distributed += referral_points
                logger.info(
                    "Created %f referral points for referrer %s",
                    referral_points,
                    referrer_id,
                )

                if total_points_distributed >= reward_session_config.max_points:
                    reward_session.end_date = current_time
                    session.commit()
                    break

        session.commit()
        logger.info("Referral points update completed.")
    except Exception as e:
        logger.error(
            "An error occurred during referral points update: %s", e, exc_info=True
        )
        logger.error(traceback.format_exc())


def adjust_referral_points_within_bounds(
    reward_session_config, total_points_distributed, referral_points
):
    referral_points = referral_points * constants.REFERRAL_POINTS_PERCENTAGE
    if total_points_distributed + referral_points > reward_session_config.max_points:
        referral_points = reward_session_config.max_points - total_points_distributed

    return referral_points


def get_user_points_by_referee_id(referral, reward_session, session):
    user_query = select(User).where(User.user_id == referral.referee_id)
    user = session.exec(user_query).first()
    if not user:
        return None
    user_points_query = (
        select(UserPoints)
        .where(UserPoints.wallet_address == user.wallet_address)
        .where(UserPoints.partner_name == constants.HARMONIX)
        .where(UserPoints.session_id == reward_session.session_id)
    )
    user_points = session.exec(user_points_query).first()
    return user_points


def update_vault_points(current_time):
    try:
        logger.info("Starting vault points update at %s", current_time)

        active_vaults_query = select(Vault).where(Vault.is_active == True)
        active_vaults = session.exec(active_vaults_query).all()

        for vault in active_vaults:
            try:
                # Get all earned points for the vault
                earned_points_query = (
                    select(UserPoints)
                    .where(UserPoints.vault_id == vault.id)
                    .where(UserPoints.partner_name == constants.HARMONIX)
                )
                earned_points = session.exec(earned_points_query).all()
                total_points = sum([point.points for point in earned_points])
                logger.info(
                    "Vault %s has earned %f points from Harmonix.",
                    vault.name,
                    total_points,
                )
                # Insert points distribution history
                point_distribution_history = PointDistributionHistory(
                    vault_id=vault.id,
                    partner_name=constants.HARMONIX,
                    point=total_points,
                    created_at=current_time,
                )
                session.add(point_distribution_history)
                session.commit()
            except Exception as e:
                logger.error(
                    "An error occurred while updating points distribution history for vault %s: %s",
                    vault.name,
                    e,
                    exc_info=True,
                )
                logger.error(traceback.format_exc())

        logger.info("Vault points distribution history update completed.")
    except Exception as e:
        logger.error(
            "An error occurred during vault points update: %s", e, exc_info=True
        )
        logger.error(traceback.format_exc())


if __name__ == "__main__":
    setup_logging_to_file("points_distribution_job_harmonix", logger=logger, level=logging.DEBUG)
    current_time = datetime.now(tz=timezone.utc)
    harmonix_distribute_points(current_time)
    update_vault_points(current_time)
