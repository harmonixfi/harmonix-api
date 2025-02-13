import logging
from datetime import datetime, timedelta, timezone
import uuid
from sqlmodel import Session, select
from models.base_rate_history import BaseRateHistory
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

MAX_POINT = 9000000
TOTAL_DAY = 180

def calculate_dynamic_base_rate():
    total_weighted_tvl = 0
    statement = select(RewardSessions).order_by(RewardSessions.start_date.desc())
    reward_session = session.exec(statement).first()

    statement = select(WTVLHistory).where(WTVLHistory.session_id == reward_session.session_id).order_by(WTVLHistory.recorded_at.desc())
    last_wtvl = session.exec(statement).first()

    statement = select(Vault)
    vaults = session.exec(statement).all()
    for vault in vaults:
        statement = select(PointsMultiplierConfig).where(PointsMultiplierConfig.vault_id == vault.id)
        multiplier = session.exec(statement).one()
        total_weighted_tvl += vault.tvl * multiplier.multiplier
    #create a new record in wtvl_history
    wtvl = WTVLHistory(session_id=reward_session.session_id, wtvl=total_weighted_tvl)
    session.add(wtvl)
    session.commit()
    logger.info(f"Total Weighted TVL: {total_weighted_tvl}")

    if last_wtvl is None:
        return
    
    point_remaining = MAX_POINT - reward_session.points_distributed
    logger.info(f"Point Remaining: {point_remaining}")

    #statement get lasted record in wtvl_history
    day_remaining = TOTAL_DAY - (datetime.now(timezone.utc) - reward_session.start_date.replace(tzinfo=timezone.utc)).days
    print(f"Day Remaining: {day_remaining}")
    roc_wtvl = last_wtvl.wtvl - total_weighted_tvl
    logger.info(f"ROC WTVL: {roc_wtvl}")
    base_rate = point_remaining / ((total_weighted_tvl * day_remaining) + 0.5*roc_wtvl*pow(day_remaining, 2))
    logger.info(f"Current Base Rate History: {base_rate}")

    #get previous base rate history
    statement = select(BaseRateHistory).where(BaseRateHistory.session_id == reward_session.session_id).order_by(BaseRateHistory.calculated_at.desc())
    base_rate_history = session.exec(statement).first()
    if base_rate_history is None:
        base_rate_history = BaseRateHistory(session_id=reward_session.session_id, base_rate=base_rate, point_distributed=reward_session.points_distributed)
        session.add(base_rate_history)
        session.commit()
        return
    
    logger.info(f"Previous Base Rate History: {base_rate_history.base_rate}")

    base_rate = min(base_rate, base_rate_history.base_rate)
    base_rate_history = BaseRateHistory(session_id=reward_session.session_id, base_rate=base_rate, point_distributed=reward_session.points_distributed)
    session.add(base_rate_history)
    session.commit()
    logger.info(f"New Base Rate History: {base_rate_history.base_rate}")


if __name__ == "__main__":
    calculate_dynamic_base_rate()