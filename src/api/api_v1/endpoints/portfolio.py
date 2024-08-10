import datetime
from typing import List

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import Session, select
from web3 import Web3

from bg_tasks.utils import calculate_roi
from core.abi_reader import read_abi
from models.user_points import UserPoints
from models.user_portfolio import PositionStatus
import schemas
from api.api_v1.deps import SessionDep
from models import Vault, UserPortfolio
from schemas import Position
from core.config import settings
from core import constants
from services.market_data import get_price
from utils.json_encoder import custom_encoder

router = APIRouter()

rockonyx_stablecoin_vault_abi = read_abi("RockOnyxStableCoin")
rockonyx_delta_neutral_vault_abi = read_abi("RockOnyxDeltaNeutralVault")
solv_vault_abi = read_abi("solv")


def create_vault_contract(vault: Vault):
    w3 = Web3(Web3.HTTPProvider(constants.NETWORK_RPC_URLS[vault.network_chain]))

    if vault.strategy_name == constants.DELTA_NEUTRAL_STRATEGY:
        contract = w3.eth.contract(
            address=vault.contract_address, abi=rockonyx_delta_neutral_vault_abi
        )
    elif vault.strategy_name == constants.OPTIONS_WHEEL_STRATEGY:
        contract = w3.eth.contract(
            address=vault.contract_address, abi=rockonyx_stablecoin_vault_abi
        )
    elif vault.slug == constants.SOLV_VAULT_SLUG:
        contract = w3.eth.contract(address=vault.contract_address, abi=solv_vault_abi)
    else:
        raise HTTPException(status_code=400, detail="Invalid vault strategy")

    return contract


def get_user_earned_points(
    session: Session, position: UserPortfolio
) -> List[schemas.EarnedPoints]:
    user_points = session.exec(
        select(UserPoints)
        .where(UserPoints.vault_id == position.vault_id)
        .where(UserPoints.wallet_address == position.user_address.lower())
    ).all()

    earned_points = []
    for user_point in user_points:
        earned_points.append(
            schemas.EarnedPoints(
                name=user_point.partner_name,
                point=user_point.points,
                created_at=(
                    custom_encoder(user_point.created_at)
                    if user_point.updated_at is None
                    else custom_encoder(user_point.updated_at)
                ),
            )
        )

    return earned_points


@router.get("/{user_address}", response_model=schemas.Portfolio)
async def get_portfolio_info(
    session: SessionDep,
    user_address: str,
    vault_id: str = Query(None, description="Vault Id"),
):
    statement = (
        select(UserPortfolio)
        .where(UserPortfolio.user_address == user_address.lower())
        .where(UserPortfolio.status == PositionStatus.ACTIVE)
    )
    if vault_id:
        statement = statement.where(UserPortfolio.vault_id == vault_id)

    user_positions = session.exec(statement).all()

    if user_positions is None or len(user_positions) == 0:
        portfolio = schemas.Portfolio(total_balance=0, pnl=0, positions=[])
        return portfolio

    positions: List[Position] = []
    total_balance = 0.0
    for pos in user_positions:
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
            vault_network=vault.network_chain,
        )

        if vault.strategy_name == constants.DELTA_NEUTRAL_STRATEGY:
            price_per_share = vault_contract.functions.pricePerShare().call()
            shares = vault_contract.functions.balanceOf(
                Web3.to_checksum_address(user_address)
            ).call()
            shares = shares / 10**6
            price_per_share = price_per_share / 10**6
        elif vault.slug == constants.SOLV_VAULT_SLUG:
            price_per_share = vault_contract.functions.pricePerShare().call()
            shares = vault_contract.functions.balanceOf(
                Web3.to_checksum_address(user_address)
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
                Web3.to_checksum_address(user_address)
            ).call()
            shares = shares / 10**6
            price_per_share = price_per_share / 10**6

        pending_withdrawal = pos.pending_withdrawal if pos.pending_withdrawal else 0
        position.total_balance = (
            shares * price_per_share + pending_withdrawal * price_per_share
        )
        position.pnl = position.total_balance - position.init_deposit

        holding_period = (datetime.datetime.now() - pos.trade_start_date).days
        position.apy = calculate_roi(
            position.total_balance,
            position.init_deposit,
            days=holding_period if holding_period > 0 else 1,
        )
        position.apy *= 100

        if vault.slug == constants.SOLV_VAULT_SLUG:
            btc_price = get_price("BTCUSDT")
            total_balance += position.total_balance * btc_price
        else:
            total_balance += position.total_balance

        # encode datetime
        position.trade_start_date = custom_encoder(pos.trade_start_date)
        position.next_close_round_date = custom_encoder(vault.next_close_round_date)

        positions.append(position)

    total_deposit = 0
    for position in positions:
        if position.slug == constants.SOLV_VAULT_SLUG:
            total_deposit += position.init_deposit * get_price("BTCUSDT")
        else:
            total_deposit += position.init_deposit

    pnl = (total_balance / total_deposit - 1) * 100

    portfolio = schemas.Portfolio(
        total_balance=total_balance, pnl=pnl, positions=positions
    )
    return portfolio
