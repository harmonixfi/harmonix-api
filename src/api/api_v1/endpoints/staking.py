from datetime import datetime, timedelta, timezone
import json
from typing import List, Optional
import uuid

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, bindparam, desc, func, text
from sqlmodel import Session, and_, select, or_
from models.staking_validators import StakingValidator
from models.user_stakings import UserStaking
from api.api_v1.deps import SessionDep
from schemas.staking_requests import (
    UpdateTotalStakedRequest,
    UpdateTotalUnstakedRequest,
)
from schemas.staking_response import StakingInfoResponse

router = APIRouter()


@router.get("/all-validator")
async def get_all_validator(session: SessionDep):
    statement = select(StakingValidator)
    stacking_validators = session.exec(statement).all()
    return stacking_validators


@router.post("/update-total-staked/")
def update_total_staked(request: UpdateTotalStakedRequest, session: SessionDep):
    user_staking = session.exec(
        select(UserStaking)
        .where(UserStaking.validator_id == request.validator_id)
        .where(UserStaking.wallet_address == request.wallet_address)
    ).first()

    if not user_staking:
        user_staking = UserStaking(
            validator_id=request.validator_id,
            wallet_address=request.wallet_address,
            total_staked=request.total_staked,
            total_unstaked=0,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(user_staking)
    else:
        user_staking.total_staked = request.total_staked
        user_staking.updated_at = datetime.now(timezone.utc)

    session.commit()
    session.refresh(user_staking)

    return {
        "message": "Total staked updated successfully",
        "user_staking": user_staking,
    }


@router.post("/update-total-unstaked")
def update_total_unstaked(request: UpdateTotalUnstakedRequest, session: SessionDep):
    user_staking = session.exec(
        select(UserStaking)
        .where(UserStaking.validator_id == request.validator_id)
        .where(UserStaking.wallet_address == request.wallet_address)
    ).first()

    if not user_staking:
        user_staking = UserStaking(
            validator_id=request.validator_id,
            wallet_address=request.wallet_address,
            total_staked=0,
            total_unstaked=request.total_unstaked,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(user_staking)
    else:
        user_staking.total_unstaked = request.total_unstaked
        user_staking.updated_at = datetime.now(timezone.utc)

    session.commit()
    session.refresh(user_staking)

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
