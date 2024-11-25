import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import func
from sqlmodel import Session, select

from core import constants
from log import setup_logging_to_console, setup_logging_to_file
from core.db import engine
from models.reward_session_config import RewardSessionConfig
from models.reward_sessions import RewardSessions
from services.bsx_service import claim_point, get_list_claim_point

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

session = Session(engine)

DURATION_IN_MINUTES = int(99620)
MAX_POINTS = int(5000000)


def reopen_reward_session_point():
    logger.info("Starting reopen reward session point function.")
    current_time = datetime.now(tz=timezone.utc)

    reward_session_query = (
        select(RewardSessions)
        .where(RewardSessions.partner_name == constants.HARMONIX)
        .where(RewardSessions.end_date == None)
    )
    reward_session = session.exec(reward_session_query).first()
    logger.info("Reward session found: %s", reward_session)

    if reward_session:
        reward_session_config_query = select(RewardSessionConfig).where(
            RewardSessionConfig.session_id == reward_session.session_id
        )
        reward_session_config = session.exec(reward_session_config_query).first()
        logger.info("Reward session config found: %s", reward_session_config)

        if reward_session_config:
            session_start_date = reward_session.start_date.replace(tzinfo=timezone.utc)
            session_end_date = (
                session_start_date
                + timedelta(minutes=reward_session_config.duration_in_minutes)
            ).replace(tzinfo=timezone.utc)

            if current_time <= session_end_date and current_time >= session_start_date:
                logger.info(f"Session {reward_session.session_name} is active.")
                return

    reward_session_query = (
        select(func.count())
        .select_from(RewardSessions)
        .where(RewardSessions.partner_name == constants.HARMONIX)
    )
    total_session = session.exec(reward_session_query).one()

    reward_session = RewardSessions(
        session_name=f"Session {total_session + 1}",
        start_date=current_time,
        partner_name=constants.HARMONIX,
        points_distributed=0,
    )
    session.add(reward_session)
    session.commit()
    logger.info("New reward session created: %s", reward_session)

    reward_session_config = RewardSessionConfig(
        session_id=reward_session.session_id,
        max_points=MAX_POINTS,
        created_at=current_time,
        duration_in_minutes=DURATION_IN_MINUTES,
    )
    session.add(reward_session_config)
    session.commit()


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file(
        app="reopen_reward_session_point", level=logging.INFO, logger=logger
    )

    reopen_reward_session_point()
