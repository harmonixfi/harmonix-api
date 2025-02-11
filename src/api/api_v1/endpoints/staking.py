from datetime import datetime, timedelta, timezone
import json
from typing import List, Optional
import uuid

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, bindparam, desc, func, text
from sqlmodel import Session, and_, select, or_
from core import constants
from models.staking_validators import StakingValidator
from models.user_stakings import UserStaking
from api.api_v1.deps import SessionDep
from schemas.staking_requests import StakingRequest
from schemas.staking_response import StakingInfoResponse, StakingValidatorResponse
from services import validao_service
from utils.web3_utils import verify_signature

router = APIRouter()


def get_staking_validator(session: SessionDep, validator_id):
    statement = select(StakingValidator).where(StakingValidator.id == validator_id)
    return session.exec(statement).first()


def get_user_staking(session: SessionDep, validator_id, wallet_address):
    return session.exec(
        select(UserStaking)
        .where(UserStaking.validator_id == validator_id)
        .where(UserStaking.wallet_address == wallet_address)
    ).first()


def update_or_create_user_staking(
    session: SessionDep, request: StakingRequest, is_stake=True
):
    user_staking = get_user_staking(
        session, request.validator_id, request.wallet_address
    )
    current_time = datetime.now(timezone.utc)

    if not user_staking:
        user_staking = UserStaking(
            validator_id=request.validator_id,
            wallet_address=request.wallet_address,
            total_staked=request.total_amount if is_stake else 0,
            total_unstaked=request.total_amount if not is_stake else 0,
            created_at=current_time,
            updated_at=current_time,
        )
        session.add(user_staking)
    else:
        if is_stake:
            user_staking.total_staked = request.total_amount
        else:
            user_staking.total_unstaked = request.total_amount
        user_staking.updated_at = current_time

    session.commit()
    session.refresh(user_staking)
    return user_staking


def process_validao_request(session: SessionDep, request: StakingRequest):
    staking_validator = get_staking_validator(session, request.validator_id)
    if staking_validator is None:
        raise HTTPException(status_code=400, detail="Validator not found")

    if staking_validator.slug == constants.VALIDAO_SLUG:
        # TODO: Verify amount action delegations HYPE
        return validao_service.stake(
            request.chain_id,
            request.wallet_address,
            request.total_amount,
            request.tx_hash,
        )
    return None


def validate_request_signature(request: StakingRequest):
    if not verify_signature(request.message, request.signature, request.wallet_address):
        raise HTTPException(status_code=400, detail="Invalid signature")


@router.get("/all-validator")
async def get_all_validator(session: SessionDep):
    statement = select(StakingValidator)
    staking_validators = session.exec(statement).all()
    return [StakingValidatorResponse(id=v.id, slug=v.slug) for v in staking_validators]


@router.post("/update-total-staked/")
def update_total_staked(request: StakingRequest, session: SessionDep):
    validate_request_signature(request)
    process_validao_request(session, request)
    user_staking = update_or_create_user_staking(session, request, is_stake=True)

    return {
        "message": "Total staked updated successfully",
        "user_staking": user_staking,
    }


@router.post("/update-total-unstaked/")
def update_total_unstaked(request: StakingRequest, session: SessionDep):
    validate_request_signature(request)
    process_validao_request(session, request)
    user_staking = update_or_create_user_staking(session, request, is_stake=False)

    return {
        "message": "Total unstaked updated successfully",
        "user_staking": user_staking,
    }


@router.get("/get-staking-info/")
def get_staking_info(wallet_address: str, session: SessionDep):
    user_stakings = session.exec(
        select(UserStaking).where(UserStaking.wallet_address == wallet_address)
    ).all()

    if not user_stakings:
        raise HTTPException(
            status_code=404, detail="No staking records found for this wallet"
        )

    return [
        StakingInfoResponse(
            validator_id=staking.validator_id,
            wallet_address=staking.wallet_address,
            total_staked=staking.total_staked or 0,
            total_unstaked=staking.total_unstaked or 0,
            created_at=staking.created_at,
            updated_at=staking.updated_at,
        )
        for staking in user_stakings
    ]
