from typing import List
from fastapi import APIRouter, HTTPException
from sqlmodel import select
from models.referral_points import ReferralPoints
from models.referralcodes import ReferralCode
from models.referrals import Referral
from models.reward_sessions import RewardSessions
from models.user import User
from models.user_portfolio import PositionStatus, UserPortfolio
from models.rewards import Reward
from models.user_points import UserPoints
import schemas
from api.api_v1.deps import SessionDep
from core import constants
from utils.api import (
    create_user_with_referral,
    get_user_by_wallet_address,
    is_valid_wallet_address,
)
from utils.json_encoder import custom_encoder

router = APIRouter()


@router.get("/users/{wallet_address}", response_model=dict)
async def get_user(session: SessionDep, wallet_address: str):
    wallet_address = wallet_address.lower()
    if not is_valid_wallet_address(wallet_address):
        raise HTTPException(status_code=400, detail="Invalid wallet address")
    user = get_user_by_wallet_address(session, wallet_address)
    return {"joined": user is not None}


@router.post("/users/join", response_model=dict)
async def join_user(session: SessionDep, user: schemas.UserJoin):
    user.user_address = user.user_address.lower()
    if not is_valid_wallet_address(user.user_address):
        raise HTTPException(status_code=400, detail="Invalid wallet address")
    valid = create_user_with_referral(user.user_address, user.referral_code, session)
    return {"valid": valid}


@router.get("/users/{wallet_address}/referral", response_model=List[str])
async def get_referral_codes(session: SessionDep, wallet_address: str):
    wallet_address = wallet_address.lower()
    if not is_valid_wallet_address(wallet_address):
        raise HTTPException(status_code=400, detail="Invalid wallet address")
    user = get_user_by_wallet_address(session, wallet_address)
    if not user:
        return []
    statement = select(ReferralCode).where(ReferralCode.user_id == user.user_id)
    referral_codes = session.exec(statement).all()
    return [referral_code.code for referral_code in referral_codes]


@router.get("/users/{wallet_address}/rewards", response_model=schemas.Rewards)
async def get_rewards(session: SessionDep, wallet_address: str):
    wallet_address = wallet_address.lower()
    if not is_valid_wallet_address(wallet_address):
        raise HTTPException(status_code=400, detail="Invalid wallet address")

    user = get_user_by_wallet_address(session, wallet_address)
    if not user:
        return {
            "reward_percentage": 0,
            "depositors": 0,
            "high_balance_depositors": 0,
        }

    statement = select(Referral).where(Referral.referrer_id == user.user_id)
    referrals = session.exec(statement).all()
    total_referees = len(referrals)

    # get wallet address of all depositors from user table by user_id
    statement = select(User).where(
        User.user_id.in_([referral.referee_id for referral in referrals])
    )
    depositors = session.exec(statement).all()
    high_balance_depositors = 0
    for depositor in depositors:
        statement = (
            select(UserPortfolio)
            .where(UserPortfolio.user_address == depositor.wallet_address)
            .where(UserPortfolio.status == PositionStatus.ACTIVE)
        )
        portfolios = session.exec(statement).all()
        for portfolio in portfolios:
            if portfolio.total_balance >= 50:
                high_balance_depositors += 1
                break

    statement = (
        select(Reward)
        .where(Reward.user_id == user.user_id)
        .where(Reward.status == constants.Status.ACTIVE)
    )
    rewards = session.exec(statement).first()
    return {
        "reward_percentage": rewards.reward_percentage,
        "depositors": total_referees,
        "high_balance_depositors": high_balance_depositors,
    }


@router.get("/users/{wallet_address}/points", response_model=List[schemas.Points])
async def get_points(session: SessionDep, wallet_address: str):
    wallet_address = wallet_address.lower()
    if not is_valid_wallet_address(wallet_address):
        raise HTTPException(status_code=400, detail="Invalid wallet address")

    user = get_user_by_wallet_address(session, wallet_address)
    if not user:
        return []

    statement = (
        select(UserPoints, RewardSessions)
        .where(UserPoints.session_id == RewardSessions.session_id)
        .where(RewardSessions.end_date == None)
        .where(UserPoints.partner_name == constants.HARMONIX)
        .where(UserPoints.wallet_address == wallet_address)
    )

    user_points = session.exec(statement).all()

    if not user_points:
        return []

    points: List[schemas.Points] = []

    # we need to group the user_points by session id and sum the points
    # for each session
    session_points = {}

    for user_point, reward_session in user_points:
        if user_point.session_id not in session_points:
            statement = (
                select(ReferralPoints)
                .where(ReferralPoints.user_id == user.user_id)
                .where(ReferralPoints.session_id == user_point.session_id)
            )
            referral_points = session.exec(statement).first()
            session_points[user_point.session_id] = schemas.Points(
                points=0,
                start_date=custom_encoder(reward_session.start_date),
                end_date=custom_encoder(reward_session.end_date),
                session_name=reward_session.session_name,
                partner_name=reward_session.partner_name,
                referral_points=referral_points.points if referral_points else 0,
            )
        session_points[user_point.session_id].points += user_point.points

    for _, point in session_points.items():
        points.append(point)

    return points
