import logging
from datetime import datetime, timedelta, timezone
import math
import uuid
from sqlmodel import Session, select
from models.base_rate_history import BaseRateHistory
from models.user_time_factor import UserTimeFactor
from models.wtvl_history import WTVLHistory
from services.market_data import get_price, get_klines
from bg_tasks.indexing_user_holding_kelpdao import get_pps
from log import setup_logging_to_console, setup_logging_to_file
from models.onchain_transaction_history import OnchainTransactionHistory
from models.point_distribution_history import PointDistributionHistory
from models.points_multiplier_config import PointsMultiplierConfig
from models.referral_points import ReferralPoints
from models.referral_points_history import ReferralPointsHistory
from models.referrals import Referral
from models.reward_session_config import RewardSessionConfig
from models.reward_sessions import RewardSessions
from models.user import User
from models.user_last_30_days_tvl import UserLast30DaysTVL
from models.user_points import UserPoints
from models.user_points_history import UserPointsHistory
from models.user_portfolio import PositionStatus, UserPortfolio
from models.vaults import Vault
from core.db import engine
from core import constants
from sqlmodel import Session, select

from utils.extension_utils import to_tx_aumount_rethink
from utils.web3_utils import get_vault_contract, parse_hex_to_int

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

session = Session(engine)

def calculate_time_factor():
    logger.info("Calculating time factor...")
    statement = select(User)
    users = session.exec(statement).all()

    statement = select(RewardSessions).order_by(RewardSessions.start_date.desc())
    reward_session = session.exec(statement).first()

    for user in users:
        statement = select(UserPortfolio).where(UserPortfolio.user_address == user.wallet_address)
        user_portfolio = session.exec(statement).all()
        if not user_portfolio:
            continue
        trade_start_date = None
        for portfolio in user_portfolio:
            if trade_start_date is None or portfolio.trade_start_date.replace(tzinfo=timezone.utc) < trade_start_date.replace(tzinfo=timezone.utc):
                trade_start_date = portfolio.trade_start_date.replace(tzinfo=timezone.utc)

        day_held = (datetime.now(timezone.utc) - max(trade_start_date, reward_session.start_date.replace(tzinfo=timezone.utc))).days
        time_factor = 1 + 0.1 * math.log(day_held + 1)
        user_time_factor = UserTimeFactor(user_portfolio_id=portfolio.id, time_factor=time_factor)
        session.add(user_time_factor)
    session.commit()



if __name__ == "__main__":
    calculate_time_factor()