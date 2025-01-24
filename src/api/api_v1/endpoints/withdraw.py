from datetime import datetime, timedelta, timezone
import json
from typing import List, Optional
import uuid

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import bindparam, func, text
from sqlmodel import Session, and_, select, or_
from web3 import Web3

from models.config_quotation import ConfigQuotation
from models.pps_history import PricePerShareHistory
from models.reward_distribution_config import RewardDistributionConfig
from models.reward_distribution_history import RewardDistributionHistory
from models.user_portfolio import UserPortfolio
from models.user_rewards import UserRewards
from models.vault_apy_breakdown import VaultAPYBreakdown
from models.whitelist_wallets import WhitelistWallet
import schemas
from api.api_v1.deps import SessionDep
from core import constants
from models import PointDistributionHistory, Vault
from models.vault_performance import VaultPerformance
from models.vaults import NetworkChain, VaultCategory, VaultMetadata
from schemas.pps_history_response import PricePerShareHistoryResponse
from schemas.vault import GroupSchema, SupportedNetwork
from schemas.vault_metadata_response import VaultMetadataResponse
from services import kelpgain_service
from core.config import settings
from services.vault_rewards_service import VaultRewardsService

router = APIRouter()

@router.get("/quote/{withdraw_value}", response_model=schemas.WithdrawQuoteResponse)
async def get_withdraw_quote(
    withdraw_value: float,
    wallet_address: str,
    session: SessionDep,
):
    #get user_portfolio = session.exec(select(UserRewards).where(UserRewards.wallet_address == wallet_address)).one_or_none()
    statement = session.exec(select(UserPortfolio).where(UserPortfolio.user_address == wallet_address)).all()
    total_deposit = 0
    total_balance = 0
    for user_portfolio in statement:
        total_deposit += user_portfolio.init_deposit
        total_balance += user_portfolio.total_balance
    profit = total_balance - total_deposit
    if profit < 0:
        profit = 0
    trading_fee = withdraw_value * float(session.exec(select(ConfigQuotation.value).where(ConfigQuotation.key == constants.TRADING_FEE)).one()) / 100
    max_slipage = withdraw_value * float(session.exec(select(ConfigQuotation.value).where(ConfigQuotation.key == constants.MAX_SLIPPAGE)).one()) / 100
    spot_perp_spread = withdraw_value * float(session.exec(select(ConfigQuotation.value).where(ConfigQuotation.key == constants.SPOT_PERP_SPREAD)).one()) / 100
    performance_fee = profit * float(session.exec(select(ConfigQuotation.value).where(ConfigQuotation.key == constants.PERFORMANCE_FEE)).one()) / 100
    management_fee = total_deposit * float(session.exec(select(ConfigQuotation.value).where(ConfigQuotation.key == constants.MANAGEMENT_FEE)).one()) / 100
    #pending withdraw= withdraw value / pps
    #mana fee = position.pnl*(10/100)*pendingwithdraw/totalshare
    total_fees = max_slipage + spot_perp_spread + performance_fee + management_fee
    estimated_withdraw_amount = withdraw_value - total_fees

    return schemas.WithdrawQuoteResponse(
        trading_fee=trading_fee,
        max_slippage=max_slipage,
        spot_perp_spread=spot_perp_spread,
        performance_fee=performance_fee,
        management_fee=management_fee,
        total_fees=total_fees,
        estimated_withdraw_amount=estimated_withdraw_amount
    )
    