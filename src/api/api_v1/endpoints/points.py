from datetime import datetime, timedelta, timezone
import json
from typing import List, Optional
import uuid

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import bindparam, func, text
from sqlmodel import Session, and_, select, or_
from web3 import Web3

from api.api_v1.endpoints.portfolio import (
    create_vault_contract,
    get_user_earned_points,
    get_user_earned_rewards,
    get_vault_position_details,
)
from models.config_quotation import ConfigQuotation
from models.pps_history import PricePerShareHistory
from models.reward_distribution_config import RewardDistributionConfig
from models.reward_distribution_history import RewardDistributionHistory
from models.user_portfolio import PositionStatus, UserPortfolio
from models.user_rewards import UserRewards
from models.vault_apy_breakdown import VaultAPYBreakdown
from models.whitelist_wallets import WhitelistWallet
import schemas
from api.api_v1.deps import SessionDep
from core import constants
from models import PointDistributionHistory, Vault
from models.vault_performance import VaultPerformance
from models.vaults import NetworkChain, VaultCategory, VaultMetadata
from schemas.portfolio import Position
from schemas.pps_history_response import PricePerShareHistoryResponse
from schemas.vault import GroupSchema, SupportedNetwork
from schemas.vault_metadata_response import VaultMetadataResponse
from services import kelpgain_service
from core.config import settings
from services.vault_rewards_service import VaultRewardsService
from utils.api import is_valid_wallet_address
from utils.json_encoder import custom_encoder

router = APIRouter()

POINT_PER_DOLLAR = 1000
@router.get("/", response_model=schemas.PointResponse)
async def get_user_points(
    wallet: str,
    amount: float,
    deposit_time: datetime,
    session: SessionDep
):
    wallet_address = wallet.lower()
    if not is_valid_wallet_address(wallet_address):
        raise HTTPException(status_code=400, detail="Invalid wallet address")
    now = datetime.now(timezone.utc)
    if deposit_time.tzinfo is None:
        deposit_time = deposit_time.replace(tzinfo=timezone.utc)
    diff = now - deposit_time
    hours = diff.total_seconds() / 3600
    points = hours * (amount / POINT_PER_DOLLAR)
    return {
        "wallet": wallet,
        "amount": amount,
        "points": points
    }