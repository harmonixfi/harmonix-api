import logging
from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select
from core import constants
from log import setup_logging_to_file
from models.campaigns import Campaign
from models.referrals import Referral
from models.rewards import Reward
from models.user import User
from models.user_portfolio import UserPortfolio
from core.db import engine


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

session = Session(engine)


def distribute_referral_101_rewards(current_time):
    with Session(engine) as session:
        campaign_101 = session.exec(
            select(Campaign).where(
                Campaign.name == constants.Campaign.REFERRAL_101.value
            )
        ).first()
        if campaign_101 is None or campaign_101.status == constants.Status.CLOSED.value:
            logger.info("No active campaign found or campaign is closed.")
            return
        logger.info(
            "Starting reward distribution job for campaign: %s", campaign_101.name
        )

        unique_referrers = []
        referrals_query = select(Referral).order_by(Referral.created_at)
        referrals = session.exec(referrals_query).all()
        logger.info("Retrieved %d referrals", len(referrals))

        for referral in referrals:
            logger.debug("Processing referral: %s", referral)
            if len(unique_referrers) >= constants.REWARD_HIGH_LIMIT:
                logger.info("Reached reward high limit, stopping further processing.")
                break

            if referral.referrer_id in unique_referrers:
                logger.debug(
                    "Referrer %s already processed, skipping.", referral.referrer_id
                )
                continue

            reward_query = (
                select(Reward)
                .where(Reward.user_id == referral.referrer_id)
                .order_by(Reward.start_date)
            )
            rewards = session.exec(reward_query).all()
            if not rewards:
                logger.debug(
                    "No rewards found for referrer %s, skipping.", referral.referrer_id
                )
                continue

            last_reward = rewards[-1]
            if last_reward.campaign_name == campaign_101.name:
                if (
                    last_reward.end_date is not None
                    and last_reward.end_date.replace(tzinfo=timezone.utc) < current_time
                ):
                    logger.debug(
                        "Last reward for referrer %s is expired, updating status and adding new reward.",
                        referral.referrer_id,
                    )
                    last_reward.status = constants.Status.CLOSED

                    referrer_query = select(User).where(
                        User.user_id == referral.referrer_id
                    )
                    referrer = session.exec(referrer_query).first()
                    if referrer is None:
                        logger.debug(
                            "No referrer found with ID %s, skipping.",
                            referral.referrer_id,
                        )
                        continue

                    new_reward = None
                    if (
                        referrer.tier == constants.UserTier.KOL.value
                        or referrer.tier == constants.UserTier.PARTNER.value
                    ):
                        new_reward = Reward(
                            user_id=referral.referrer_id,
                            referral_code_id=referral.referral_code_id,
                            reward_percentage=constants.REWARD_KOL_AND_PARTNER_DEFAULT_PERCENTAGE,
                            start_date=current_time,
                            end_date=None,
                            campaign_name=constants.Campaign.KOL_AND_PARTNER.value,
                        )
                    else:
                        new_reward = Reward(
                            user_id=referral.referrer_id,
                            referral_code_id=referral.referral_code_id,
                            reward_percentage=constants.REWARD_DEFAULT_PERCENTAGE,
                            start_date=current_time,
                            end_date=None,
                            campaign_name=constants.Campaign.DEFAULT.value,
                        )

                    session.add(new_reward)
                    session.commit()
                    logger.debug(
                        "New reward added for referrer %s", referral.referrer_id
                    )
                unique_referrers.append(referral.referrer_id)
                continue

            user_query = select(User).where(User.user_id == referral.referee_id)
            user = session.exec(user_query).first()
            if not user:
                logger.debug("No user found with ID %s, skipping.", referral.referee_id)
                continue

            user_portfolio_query = select(UserPortfolio).where(
                UserPortfolio.user_address == user.wallet_address
            )
            user_portfolios = session.exec(user_portfolio_query).all()
            for user_portfolio in user_portfolios:
                if user_portfolio.total_balance >= constants.MIN_FUNDS_FOR_HIGH_REWARD:
                    logger.debug(
                        "User portfolio balance is sufficient for high reward, processing referrer %s",
                        referral.referrer_id,
                    )
                    last_reward.status = constants.Status.CLOSED
                    last_reward.end_date = current_time
                    high_reward = Reward(
                        user_id=referral.referrer_id,
                        referral_code_id=referral.referral_code_id,
                        reward_percentage=constants.REWARD_HIGH_PERCENTAGE,
                        start_date=current_time,
                        end_date=current_time
                        + timedelta(constants.HIGH_REWARD_DURATION_DAYS),
                        campaign_name=campaign_101.name,
                    )
                    session.add(high_reward)
                    session.commit()
                    logger.debug(
                        "High reward added for referrer %s", referral.referrer_id
                    )
                    unique_referrers.append(referral.referrer_id)
                    break

        logger.info("Reward distribution job completed.")


if __name__ == "__main__":
    setup_logging_to_file("reward_distribution_job", logger=logger, level=logging.DEBUG)
    current_time = datetime.now(timezone.utc)
    logger.info("Job started at %s", current_time)
    distribute_referral_101_rewards(current_time)
    logger.info("Job finished at %s", datetime.now(timezone.utc))
