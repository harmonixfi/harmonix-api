import logging
from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select
from models.referrals import Referral
from models.rewards import Reward
from models.user import User
from models.user_portfolio import UserPortfolio
from core.db import engine
from sqlmodel import Session, select


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

session = Session(engine)


def reward_distribution_job():
    with Session(engine) as session:
        logger.info("Starting reward distribution job...")
        current_time = datetime.now(timezone.utc)
        unique_referrers = []
        referrals_query = select(Referral).order_by(Referral.created_at)
        referrals = session.exec(referrals_query).all()
        for referral in referrals:
            if len(unique_referrers) >= constants.REWARD_HIGH_LIMIT:
                break
            if referral.referrer_id in unique_referrers:
                continue
            reward_query = select(Reward).where(Reward.user_id == referral.referrer_id).order_by(Reward.start_date)
            rewards = session.exec(reward_query).all()
            last_reward = rewards[-1]
            if rewards is None:
                continue
            if len(rewards) > 1:
                if last_reward.reward_percentage == constants.REWARD_HIGH_PERCENTAGE:
                    if last_reward.end_date is not None and last_reward.end_date.replace(tzinfo=timezone.utc) < current_time:
                        last_reward.status = constants.Status.CLOSED
                        new_reward = Reward(
                            user_id=referral.referrer_id,
                            referral_code_id=referral.referral_code_id,
                            reward_percentage=constants.REWARD_DEFAULT_PERCENTAGE,
                            start_date=current_time,
                            end_date=None,
                        )
                        session.add(new_reward)
                        session.commit()
                unique_referrers.append(referral.referrer_id)
                continue
            user_query = select(User).where(User.user_id == referral.referee_id)
            user = session.exec(user_query).first()
            if not user:
                continue
            user_portfolio_query = select(UserPortfolio).where(
                UserPortfolio.user_address == user.wallet_address
            )
            user_portfolios = session.exec(user_portfolio_query).all()
            for user_portfolio in user_portfolios:
                if (
                    user_portfolio.total_balance
                    >= constants.MIN_FUNDS_FOR_HIGH_REWARD
                ):
                    last_reward.status = constants.Status.CLOSED
                    last_reward.end_date = current_time
                    high_reward = Reward(
                        user_id=referral.referrer_id,
                        referral_code_id=referral.referral_code_id,
                        reward_percentage=constants.REWARD_HIGH_PERCENTAGE,
                        start_date=current_time,
                        end_date=current_time
                        + timedelta(constants.HIGH_REWARD_DURATION_DAYS),
                    )
                    session.add(high_reward)
                    session.commit()
                    unique_referrers.append(referral.referrer_id)
                    break
        logger.info("Reward distribution job completed.")


# Example usage
if __name__ == "__main__":
    reward_distribution_job()
