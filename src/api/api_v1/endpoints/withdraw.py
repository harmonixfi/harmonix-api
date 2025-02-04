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

from api.api_v1.endpoints.portfolio import create_vault_contract, get_user_earned_points, get_user_earned_rewards
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
from utils.json_encoder import custom_encoder

router = APIRouter()

@router.get("/quote/{withdraw_value}", response_model=schemas.WithdrawQuoteResponse)
async def get_withdraw_quote(
    withdraw_value: float,
    wallet_address: str,
    vault_id: str,
    session: SessionDep,
):
    statement = (
        select(UserPortfolio)
        .where(UserPortfolio.user_address == wallet_address.lower())
        .where(UserPortfolio.status == PositionStatus.ACTIVE)
    )
    if vault_id:
        statement = statement.where(UserPortfolio.vault_id == vault_id)

    pos = session.exec(statement).one()
    vault = session.exec(select(Vault).where(Vault.id == pos.vault_id)).one()

    vault_contract = create_vault_contract(vault)

    position = Position(
        id=pos.id,
        vault_id=pos.vault_id,
        user_address=pos.user_address,
        vault_address=vault.contract_address,
        total_balance=pos.total_balance,
        init_deposit=(
            pos.init_deposit + pos.pending_withdrawal * pos.entry_price
            if pos.pending_withdrawal
            else pos.init_deposit
        ),
        entry_price=pos.entry_price,
        pnl=pos.pnl,
        status=pos.status,
        pending_withdrawal=pos.pending_withdrawal,
        vault_name=vault.name,
        vault_currency=vault.vault_currency,
        current_round=vault.current_round,
        monthly_apy=vault.monthly_apy,
        weekly_apy=vault.weekly_apy,
        slug=vault.slug,
        initiated_withdrawal_at=custom_encoder(pos.initiated_withdrawal_at),
        points=get_user_earned_points(session, pos),
        rewards=get_user_earned_rewards(session=session, position=pos),
        vault_network=vault.network_chain,
    )

    if vault.category == VaultCategory.real_yield_v2:
        price_per_share = vault_contract.functions.pricePerShare().call()
        shares = vault_contract.functions.balanceOf(
            Web3.to_checksum_address(wallet_address)
        ).call()
        shares = shares / 10**18
        price_per_share = price_per_share / 10**18
    elif vault.strategy_name in {
        constants.DELTA_NEUTRAL_STRATEGY,
        constants.PENDLE_HEDGING_STRATEGY,
    }:
        price_per_share = vault_contract.functions.pricePerShare().call()
        shares = vault_contract.functions.balanceOf(
            Web3.to_checksum_address(wallet_address)
        ).call()
        shares = shares / 10**6
        price_per_share = price_per_share / 10**6
    elif vault.slug == constants.SOLV_VAULT_SLUG:
        price_per_share = vault_contract.functions.pricePerShare().call()
        shares = vault_contract.functions.balanceOf(
            Web3.to_checksum_address(wallet_address)
        ).call()
        shares = shares / 10**18
        price_per_share = price_per_share / 10**8
    else:
        # calculate next Friday from today
        position.next_close_round_date = (
            datetime.datetime.now()
            + datetime.timedelta(days=(4 - datetime.datetime.now().weekday()) % 7)
        ).replace(hour=8, minute=0, second=0)

        price_per_share = vault_contract.functions.pricePerShare().call()
        shares = vault_contract.functions.balanceOf(
            Web3.to_checksum_address(wallet_address)
        ).call()
        shares = shares / 10**6
        price_per_share = price_per_share / 10**6

    pending_withdrawal = pos.pending_withdrawal if pos.pending_withdrawal else 0

    if vault.category == VaultCategory.real_yield_v2:
        position.total_balance = (
            (shares * price_per_share)
            + (pos.pending_deposit)
            + (pending_withdrawal * price_per_share)
        )
    else:
        position.total_balance = (
            shares * price_per_share + pending_withdrawal * price_per_share
        )

    position.pnl = position.total_balance - position.init_deposit

    #get user_portfolio = session.exec(select(UserRewards).where(UserRewards.wallet_address == wallet_address)).one_or_none()
    statement = session.exec(select(UserPortfolio).where(UserPortfolio.user_address == wallet_address)).all()
    total_deposit = 0
    total_balance = 0
    for user_portfolio in statement:
        total_deposit += user_portfolio.init_deposit
        total_balance += user_portfolio.total_balance
    trading_fee = withdraw_value * float(session.exec(select(ConfigQuotation.value).where(ConfigQuotation.key == constants.TRADING_FEE)).one()) / 100
    max_slipage = withdraw_value * float(session.exec(select(ConfigQuotation.value).where(ConfigQuotation.key == constants.MAX_SLIPPAGE)).one()) / 100
    spot_perp_spread = withdraw_value * float(session.exec(select(ConfigQuotation.value).where(ConfigQuotation.key == constants.SPOT_PERP_SPREAD)).one()) / 100
    performance_fee = position.pnl * float(session.exec(select(ConfigQuotation.value).where(ConfigQuotation.key == constants.PERFORMANCE_FEE)).one()) / 100
    if position.pnl < 0:
        performance_fee = 0
    management_fee = float(session.exec(select(ConfigQuotation.value).where(ConfigQuotation.key == constants.MANAGEMENT_FEE)).one()) / 100
    pending_withdraw= withdraw_value / price_per_share
    # management_fee = management_fee*pending_withdraw/totalshare
    management_fee = management_fee * position.total_balance
    #withdraw/total_balance *(today - pos.createdat)*1/100/365
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
    