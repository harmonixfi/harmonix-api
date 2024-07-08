from core import constants
from datetime import datetime, timezone
import uuid
from models.referralcodes import ReferralCode
from models.referrals import Referral
from models.rewards import Reward
from models.user import User
from sqlmodel import select
import secrets
import string
from eth_utils import is_address, to_checksum_address

def is_valid_wallet_address(wallet_address):
        if not is_address(wallet_address):
                return False
        return to_checksum_address(wallet_address)


def generate_referral_code(length=8):
    # Define the characters that can be used in the referral code
    characters = string.ascii_letters + string.digits

    # Generate a secure random string with the specified length = 10
    referral_code = "".join(secrets.choice(characters) for _ in range(length))

    return referral_code


def get_user_by_wallet_address(session, wallet_address):
    statement = select(User).where(User.wallet_address == wallet_address)
    user = session.exec(statement).first()
    return user


def create_user_with_referral(user_address, referral_code, session):
    user = get_user_by_wallet_address(session, user_address)
    if user:
        return False
    referral = get_referral_by_code(session, referral_code)
    if not referral:
        return False
    if referral.usage_limit <= 0:
        return False
    referral.usage_limit -= 1
    user = User(user_id=uuid.uuid4(), wallet_address=user_address)
    session.add(user)
    create_referral_code(session, user)

    new_referral = Referral(
        referrer_id=referral.user_id,
        referee_id=user.user_id,
        referral_code_id=referral.referral_code_id,
    )
    session.add(new_referral)
    new_reward = Reward(
        user_id=referral.user_id,
        referral_code_id=referral.referral_code_id,
        reward_percentage=constants.REWARD_DEFAULT_PERCENTAGE,
        start_date=datetime.now(timezone.utc),
        end_date=None,
    )
    session.add(new_reward)
    session.commit()
    return True


def get_referral_by_code(session, code):
    statement = select(ReferralCode).where(ReferralCode.code == code)
    referral = session.exec(statement).first()
    return referral


def create_referral_code(session, user):
    new_referral_code = ReferralCode(
        referral_code_id=uuid.uuid4(),
        user_id=user.user_id,
        code=generate_referral_code(),
        usage_limit=50,
    )
    statement = select(ReferralCode).where(ReferralCode.code == new_referral_code.code)
    referral = session.exec(statement).first()
    if referral:
        create_referral_code(session, user)
        return

    session.add(new_referral_code)
