import logging
from datetime import datetime, timedelta, timezone
import uuid
from sqlmodel import Session, select
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


def calculate_tvl_last_30_days():
    logger.info("Starting calculate TVL last 30 days job...")
    now = datetime.now().timestamp()
    last_30_days_timestamp = now - 30 * 24 * 60 * 60
    users = session.exec(select(User)).all()
    vaults = session.exec(select(Vault).where(Vault.is_active)).all()
    vaults_dict = {vault.contract_address.lower(): vault for vault in vaults}
    for user in users:
        statement = select(Referral).where(Referral.referrer_id == user.user_id)
        referrals = session.exec(statement).all()
        if len(referrals) == 0:
            continue
        shares_deposited = 0
        balance_deposited = 0
        shares_withdraw = 0
        for referral in referrals:
            statement = select(User).where(User.user_id == referral.referee_id)
            referee = session.exec(statement).first()
            statement = (
                select(OnchainTransactionHistory)
                .where(OnchainTransactionHistory.timestamp >= last_30_days_timestamp)
                .where(OnchainTransactionHistory.from_address == referee.wallet_address)
            )

            onchain_transaction_histories = session.exec(statement).all()
            if len(onchain_transaction_histories) == 0:
                continue

            for onchain_transaction_history in onchain_transaction_histories:
                vault_object = vaults_dict.get(
                    onchain_transaction_history.to_address.lower()
                )

                if (
                    onchain_transaction_history.method_id
                    == constants.MethodID.DEPOSIT.value
                ):
                    pps = get_pps_by_vault(onchain_transaction_history, vaults)
                    if pps is None:
                        continue
                    input_data = onchain_transaction_history.input[10:].lower()
                    amount = input_data[:64]
                    tokenIn = input_data[64:128]
                    tokenIn = f"0x{tokenIn[24:]}"
                    amount = parse_hex_to_int(amount)
                    if tokenIn == constants.DAI_CONTRACT_ADDRESS:
                        deposit = amount / 1e18
                    else:
                        deposit = amount / 1e6
                    balance_deposited += deposit
                    shares_deposited += deposit / pps

                elif (
                    onchain_transaction_history.method_id
                    == constants.MethodID.DEPOSIT2.value
                    and vault_object
                    and vault_object.name == constants.VAULT_SOLV_NAME
                ):
                    pps = get_pps_by_vault(onchain_transaction_history, vaults)
                    if pps is None:
                        continue

                    deposit = calculate_amount_value_for_solv(
                        onchain_transaction_history
                    )
                    balance_deposited += deposit
                    shares_deposited += deposit / pps

                elif (
                    onchain_transaction_history.method_id
                    in [
                        constants.MethodID.DEPOSIT_RETHINK1.value,
                        constants.MethodID.DEPOSIT_RETHINK2.value,
                    ]
                    and vault_object
                    and vault_object.slug == constants.ETH_WITH_LENDING_BOOST_YIELD
                ):
                    pps = get_pps_by_vault(onchain_transaction_history, vaults)
                    if pps is None:
                        continue
                    deposit = calculate_amount_value_for_rethink(
                        onchain_transaction_history
                    )
                    balance_deposited += deposit
                    shares_deposited += deposit / pps
                elif (
                    onchain_transaction_history.method_id
                    == constants.MethodID.WITHDRAW.value
                ):
                    if vault_object and vault_object.name == constants.VAULT_SOLV_NAME:
                        withdraw = calculate_amount_value_for_solv(
                            onchain_transaction_history
                        )
                    else:
                        amount = parse_hex_to_int(
                            onchain_transaction_history.input[10:]
                        )
                        withdraw = amount / 1e6
                    shares_withdraw += withdraw

        if balance_deposited == 0:
            user_last_30_days_tvl = UserLast30DaysTVL(
                user_id=user.user_id,
                avg_entry_price=0,
                shares_deposited=0,
                shares_withdraw=shares_withdraw,
                total_value_locked=0,
            )
            session.add(user_last_30_days_tvl)
            session.commit()
            continue

        avg_entry_price = balance_deposited / shares_deposited
        balance_withdraw = shares_withdraw * avg_entry_price
        tvl = balance_deposited - balance_withdraw
        if tvl < 0:
            tvl = 0

        user_last_30_days_tvl = UserLast30DaysTVL(
            user_id=user.user_id,
            avg_entry_price=avg_entry_price,
            shares_deposited=shares_deposited,
            shares_withdraw=shares_withdraw,
            total_value_locked=tvl,
        )
        session.add(user_last_30_days_tvl)
        session.commit()

    logger.info("Calculate TVL last 30 days job completed.")


def calculate_amount_value_for_solv(onchain_transaction_history):
    input_data = onchain_transaction_history.input[10:].lower()
    amount = input_data[:64]
    amount = parse_hex_to_int(amount)
    amount = amount / 1e8
    converted_datetime = datetime.fromtimestamp(onchain_transaction_history.timestamp)
    btc_price = float(
        get_klines(
            "BTCUSDT",
            start_time=converted_datetime,
            end_time=converted_datetime.utcnow() + timedelta(minutes=15),
            interval="15m",
            limit=1,
        )[0][4]
    )
    amount = amount * btc_price
    return amount


def calculate_amount_value_for_rethink(onchain_transaction_history):
    converted_datetime = datetime.fromtimestamp(onchain_transaction_history.timestamp)
    if (
        onchain_transaction_history.method_id
        == constants.MethodID.DEPOSIT_RETHINK1.value
    ):
        amount = float(onchain_transaction_history.value)
    else:
        amount = to_tx_aumount_rethink(onchain_transaction_history.input)
    wEth_price = float(
        get_klines(
            "ETHUSDT",
            start_time=converted_datetime,
            end_time=converted_datetime.utcnow() + timedelta(minutes=15),
            interval="15m",
            limit=1,
        )[0][4]
    )
    amount = amount * wEth_price
    return amount


def get_pps_by_vault(onchain_tx: OnchainTransactionHistory, vaults: list[Vault]):
    for vault in vaults:
        if vault.contract_address.lower() == onchain_tx.to_address:
            vault_contract, _ = get_vault_contract(vault)
            pps = get_pps(vault_contract, onchain_tx.block_number)
            return pps


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file(f"calculate_tvl_last_30_days", logger=logger)
    calculate_tvl_last_30_days()
