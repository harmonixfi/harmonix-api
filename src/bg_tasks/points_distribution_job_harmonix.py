import logging
from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select
from uuid import UUID
from log import setup_logging_to_file
from models.points_multiplier_config import PointsMultiplierConfig
from models.reward_session_config import RewardSessionConfig
from models.reward_sessions import RewardSessions
from models.user_points import UserPoints
from models.user_points_history import UserPointsHistory
from models.user_portfolio import PositionStatus, UserPortfolio
from models.vaults import Vault
from core.db import engine
from core.config import settings
from sqlmodel import Session, select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PARTNER_NAME = "Harmonix"
session = Session(engine)


def harmonix_distribute_points():
    current_time = datetime.now(tz=timezone.utc)
    # get reward session with end_date = null, and partner_name = Harmonix
    reward_session_query = (
        select(RewardSessions)
        .where(RewardSessions.partner_name == PARTNER_NAME)
        .where(RewardSessions.end_date == None)
    )
    reward_session = session.exec(reward_session_query).first()

    if not reward_session:
        logger.info("No active reward session found for Harmonix.")
        return

    # get reward session config
    reward_session_config_query = select(RewardSessionConfig).where(
        RewardSessionConfig.session_id == reward_session.session_id
    )
    reward_session_config = session.exec(reward_session_config_query).first()
    if not reward_session_config:
        logger.info("No reward session config found for Harmonix.")
        return

    session_start_date = reward_session_config.config_date + timedelta(
        days=reward_session_config.start_delay_days
    )
    session_start_date = session_start_date.replace(tzinfo=timezone.utc)
    if current_time < session_start_date:
        logger.info("Session 1 has not started yet.")
        return

    # select all user points distributed where partner_name is Harmonix and created_at is greater than or equal to SESSION_1_START_DATE
    session_1_points_query = (
        select(UserPoints)
        .where(UserPoints.partner_name == PARTNER_NAME)
        .where(UserPoints.created_at >= session_start_date)
    )
    
    total_points_distributed = sum([user_points.points for user_points in session.exec(session_1_points_query).all()])

    if total_points_distributed >= reward_session_config.max_points:
        logger.info("Maximum points for Session 1 have been distributed.")
        return

    # Fetch active user portfolios
    active_portfolios_query = select(UserPortfolio).where(
        UserPortfolio.status == PositionStatus.ACTIVE
    )
    active_portfolios = session.exec(active_portfolios_query).all()
    active_portfolios.sort(key=lambda x: x.trade_start_date)
    for portfolio in active_portfolios:
        vault_query = select(Vault).where(Vault.id == portfolio.vault_id)
        vault = session.exec(vault_query).first()

        if not vault:
            continue

        # Get the multiplier for the vault category
        multiplier_query = select(PointsMultiplierConfig).where(
            PointsMultiplierConfig.vault_id == vault.id
        )
        multiplier_config = session.exec(multiplier_query).first()

        if not multiplier_config:
            continue
        multiplier = multiplier_config.multiplier

        #get user points distributed for the user by wallet_address
        user_points_query = (
            select(UserPoints)
            .where(UserPoints.wallet_address == portfolio.user_address)
            .where(UserPoints.partner_name == PARTNER_NAME)
            .where(UserPoints.session_id == reward_session.session_id)
            .where(UserPoints.vault_id == portfolio.vault_id)
        )
        user_points = session.exec(user_points_query).first()
        #if  user points is none then insert user points
        if not user_points:
            # Calculate points to be distributed
            duration_hours = (
                current_time - portfolio.trade_start_date.replace(tzinfo=timezone.utc)
            ).total_seconds() / 3600
            points = (portfolio.total_balance / 100) * duration_hours * multiplier

            # Check if the total points exceed the maximum allowed
            if total_points_distributed + points > reward_session_config.max_points:
                points = reward_session_config.max_points - total_points_distributed

            # Create UserPoints entry
            user_points = UserPoints(
                vault_id=portfolio.vault_id,
                wallet_address=portfolio.user_address,
                points=points,
                partner_name=PARTNER_NAME,
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

            if total_points_distributed >= reward_session_config.max_points:
                break
        else:
            #get last user points history
            user_points_history_query = (
                select(UserPointsHistory)
                .where(UserPointsHistory.user_points_id == user_points.id)
                .order_by(UserPointsHistory.created_at.desc())
            )
            user_points_history = session.exec(user_points_history_query).first()
            # Calculate points to be distributed
            duration_hours = (
                current_time - user_points_history.created_at.replace(tzinfo=timezone.utc)
            ).total_seconds() / 3600
            points = (portfolio.total_balance / 100) * duration_hours * multiplier
            points+=1000
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
    logger.info("Points distribution job completed.")


if __name__ == "__main__":
    harmonix_distribute_points()
