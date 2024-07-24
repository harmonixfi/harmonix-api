import logging
from datetime import datetime, timedelta, timezone
import uuid
from sqlmodel import Session, select

from bg_tasks.indexing_user_holding_kelpdao import get_pps
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

from utils.web3_utils import get_vault_contract, parse_hex_to_int

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

session = Session(engine)
DAI_CONTRACT_ADDRESS = "000000000000000000000000da10009cbd5d07dd0cecc66161fc93d7c9000da1"
def calculate_tvl_last_30_days():
    logger.info("Starting calculate TVL last 30 days job...")
    now = datetime.now().timestamp()
    last_30_days_timestamp = now - 30 * 24 * 60 * 60
    statement = select(User)
    users = session.exec(statement).all()
    statement = select(Vault)
    vaults = session.exec(statement).all()

    for user in users:
        statement = select(Referral).where(Referral.referrer_id == user.user_id)
        referrals = session.exec(statement).all()
        if len(referrals) == 0:
            continue
        share_deposited =0
        balance_deposited = 0
        share_withdraw = 0
        for referral in referrals:
            statement  =select(User).where(User.user_id == referral.referee_id)
            referee = session.exec(statement).first()
            statement = select(OnchainTransactionHistory).where(OnchainTransactionHistory.timestamp >= last_30_days_timestamp).where(OnchainTransactionHistory.from_address == referee.wallet_address)
            onchain_transaction_histories = session.exec(statement).all()
            if len(onchain_transaction_histories) == 0:
                continue
            for onchain_transaction_historie in onchain_transaction_histories:
                if onchain_transaction_historie.method_id == '0xb6b55f25':
                    pps = get_pps_by_vault(onchain_transaction_historie,vaults)
                    input = parse_hex_to_int(onchain_transaction_historie.input[10:])
                    deposit = input/1e6
                    balance_deposited += deposit
                    share_deposited += deposit / pps
                elif onchain_transaction_historie.method_id == '0x2e2d2984':
                    pps = get_pps_by_vault(onchain_transaction_historie,vaults)
                    if pps is None:
                        continue
                    input = parse_hex_to_int(onchain_transaction_historie.input[10:74])
                    if DAI_CONTRACT_ADDRESS in onchain_transaction_historie.input:
                        deposit = input/1e18
                    else:
                        deposit = input/1e6
                    balance_deposited += deposit
                    share_deposited += deposit / pps
                elif onchain_transaction_historie.method_id == '0x12edde5e':
                    input = parse_hex_to_int(onchain_transaction_historie.input[10:])
                    withdraw = input/1e6
                    share_withdraw += withdraw
        if balance_deposited == 0:
            if share_deposited == 0:
                tvl = 0
                continue
            tvl = share_deposited
            continue
        weighted_median_share = balance_deposited / share_deposited
        balance_withdraw = share_withdraw * weighted_median_share
        tvl = balance_deposited - balance_withdraw
        user_last_30_days_tvl = UserLast30DaysTVL(
            user_id=user.user_id,
            weighted_median_share=weighted_median_share,
            share_deposited=share_deposited,
            share_withdraw=share_withdraw,
            total_value_locked=tvl
        )
        session.add(user_last_30_days_tvl)
        session.commit()
    logger.info("Calculate TVL last 30 days job completed.")

def get_pps_by_vault(onchain_transaction_historie,vaults):
    for vault in vaults:
        if vault.contract_address.lower() == onchain_transaction_historie.to_address:
            vault_contract, w3 = get_vault_contract(vault)
            pps = get_pps(vault_contract,onchain_transaction_historie.block_number)
            return pps






if __name__ == "__main__":
    calculate_tvl_last_30_days()