import logging
from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select
from core import constants
from models.referrals import Referral
from models.reward_thresholds import RewardThresholds
from models.rewards import Reward
from models.user import User
from models.user_monthly_tvl import UserMonthlyTVL
from models.user_portfolio import UserPortfolio
from core.db import engine
from sqlmodel import Session, select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
session = Session(engine)
def calculate_monthly_tvl():
    logger.info("Starting monthly TVL calculation job...")
    current_time = datetime.now(timezone.utc)
    unique_referrers = []
    referrals_query = select(Referral).order_by(Referral.created_at)
    referrals = session.exec(referrals_query).all()
    for referral in referrals:
        if referral.referrer_id in unique_referrers:
            continue

        referrer_query = select(User).where(User.user_id == referral.referrer_id)
        referrer = session.exec(referrer_query).first()
        if not referrer:
            continue

        user_query = select(User).where(User.user_id == referral.referee_id)
        user = session.exec(user_query).first()
        if not user:
            continue

        user_portfolio_query = select(UserPortfolio).where(
            UserPortfolio.user_address == user.wallet_address
        )
        monthly_tvl = 0
        user_portfolios = session.exec(user_portfolio_query).all()
        for user_portfolio in user_portfolios:
            monthly_tvl += user_portfolio.total_balance
            unique_referrers.append(referral.referrer_id)
    logger.info("Monthly TVL calculation job completed.")

if __name__ == "__main__":
    calculate_monthly_tvl()
