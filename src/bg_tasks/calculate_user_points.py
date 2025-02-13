import logging
from datetime import datetime, timedelta, timezone
import math
import uuid
from sqlmodel import Session, select
from models.base_rate_history import BaseRateHistory
from models.user_season_1_points import UserSeason1Points
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


def calculate_user_points():
    logger.info("Calculating user points...")
    statement = select(User)
    users = session.exec(statement).all()
    for user in users:
        #get user points in user season 1 points
        statement = select(UserSeason1Points).where(UserSeason1Points.user_id == user.user_id)
        user_season_1_points = session.exec(statement).first()

        loyalty_bonus = 0.015 * math.log(user_season_1_points.points + 1)
        print(loyalty_bonus)



if __name__ == "__main__":
    calculate_user_points()