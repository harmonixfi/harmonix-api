import datetime
from typing import List

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func
from sqlmodel import Session, select
from web3 import Web3

from bg_tasks.utils import calculate_roi
from core.abi_reader import read_abi
from models.reward_distribution_config import RewardDistributionConfig
from models.user_points import UserPoints
from models.user_portfolio import PositionStatus
from models.user_rewards import UserRewards
from models.vaults import VaultCategory
import schemas
from api.api_v1.deps import SessionDep
from models import Vault, UserPortfolio
from schemas import Position
from core.config import settings
from core import constants
from services.market_data import get_price
from utils.json_encoder import custom_encoder
from utils.vault_utils import get_vault_currency_price

router = APIRouter()

rockonyx_stablecoin_vault_abi = read_abi("RockOnyxStableCoin")
rockonyx_delta_neutral_vault_abi = read_abi("RockOnyxDeltaNeutralVault")
solv_vault_abi = read_abi("solv")
pendlehedging_vault_abi = read_abi("pendlehedging")
rethink_vault_abi = read_abi("rethink_yield_v2")
hype_abi = read_abi("hype")
kelpdao_abi = read_abi("kelpdao")


def create_vault_contract(vault: Vault):
    w3 = Web3(Web3.HTTPProvider(constants.NETWORK_RPC_URLS[vault.network_chain]))

    if vault.category == VaultCategory.real_yield_v2:
        contract = w3.eth.contract(
            address=vault.contract_address, abi=rethink_vault_abi
        )
    elif vault.slug == constants.HYPE_DELTA_NEUTRAL_SLUG:
        contract = w3.eth.contract(address=vault.contract_address, abi=hype_abi)
    elif (
        vault.slug == constants.KELPDAO_GAIN_VAULT_SLUG
        or vault.slug == constants.KELPDAO_VAULT_ARBITRUM_SLUG
    ):
        contract = w3.eth.contract(address=vault.contract_address, abi=kelpdao_abi)
    elif vault.strategy_name == constants.DELTA_NEUTRAL_STRATEGY:
        contract = w3.eth.contract(
            address=vault.contract_address, abi=rockonyx_delta_neutral_vault_abi
        )
    elif vault.strategy_name == constants.OPTIONS_WHEEL_STRATEGY:
        contract = w3.eth.contract(
            address=vault.contract_address, abi=rockonyx_stablecoin_vault_abi
        )
    elif vault.slug == constants.SOLV_VAULT_SLUG:
        contract = w3.eth.contract(address=vault.contract_address, abi=solv_vault_abi)
    elif vault.strategy_name == constants.PENDLE_HEDGING_STRATEGY:
        contract = w3.eth.contract(
            address=vault.contract_address, abi=pendlehedging_vault_abi
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid vault strategy")

    return contract


def get_user_earned_points(
    session: Session, position: UserPortfolio
) -> List[schemas.EarnedPoints]:
    user_points = session.exec(
        select(
            UserPoints.partner_name.label("partner_name"),
            func.sum(UserPoints.points).label("points"),
        )
        .where(UserPoints.vault_id == position.vault_id)
        .where(UserPoints.wallet_address == position.user_address.lower())
        .group_by(UserPoints.partner_name)
    ).all()
    earned_points = []
    for user_point in user_points:
        earned_points.append(
            schemas.EarnedPoints(
                name=user_point.partner_name,
                point=user_point.points,
                created_at=None,
            )
        )

    return earned_points


def _get_name_token_reward(session: Session, vault_id) -> str:
    """
    Retrieve the reward token name for a given vault.

    Args:
        session (Session): The database session.

    Returns:
        str: The reward token name. Returns an empty string if no reward token is found.
    """
    statement = select(RewardDistributionConfig.reward_token).where(
        RewardDistributionConfig.vault_id == vault_id
    )
    reward_token = session.exec(statement).first()

    return reward_token


def get_user_earned_rewards(
    session: Session, position: UserPortfolio
) -> List[schemas.UserEarnedRewards]:
    total_reward = session.exec(
        select(
            func.sum(UserRewards.total_reward),
        )
        .where(UserRewards.vault_id == position.vault_id)
        .where(UserRewards.wallet_address == position.user_address.lower())
    ).one()

    earned_rewards = []
    token_name = _get_name_token_reward(session, position.vault_id)
    if token_name:
        earned_rewards.append(
            schemas.UserEarnedRewards(
                name=token_name,
                unclaim=total_reward if total_reward else 0,
                claimed=0,
                created_at=None,
            )
        )

    return earned_rewards


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
            rewards=get_user_earned_rewards(session=session, position=pos),
            vault_network=vault.network_chain,
        )

        if vault.category == VaultCategory.real_yield_v2:
            price_per_share = vault_contract.functions.pricePerShare().call()
            shares = vault_contract.functions.balanceOf(
                Web3.to_checksum_address(user_address)
            ).call()
            shares = shares / 10**18
            price_per_share = price_per_share / 10**18
        elif vault.strategy_name in {
            constants.DELTA_NEUTRAL_STRATEGY,
            constants.PENDLE_HEDGING_STRATEGY,
        }:
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

        holding_period = (datetime.datetime.now() - pos.trade_start_date).days
        # Ensure non-negative PNL and APY for first 10 days
        if holding_period <= 10:
            position.pnl = max(position.pnl, 0)

        position.apy = calculate_roi(
            position.total_balance,
            position.init_deposit,
            days=holding_period if holding_period > 0 else 1,
        )
        position.apy *= 100

        # Ensure non-negative APY for first 10 days
        if holding_period <= 10:
            position.total_balance = max(position.init_deposit, position.total_balance)
            position.apy = max(position.apy, 0)

        # if vault.slug == constants.SOLV_VAULT_SLUG:
        #     btc_price = get_price("BTCUSDT")
        #     total_balance += position.total_balance * btc_price
        # else:
        #     total_balance += position.total_balance
        currency_price = get_vault_currency_price(vault.vault_currency)
        if vault.slug in [
            constants.KELPDAO_GAIN_VAULT_SLUG,
            constants.KELPDAO_VAULT_ARBITRUM_SLUG,
            constants.HYPE_DELTA_NEUTRAL_SLUG,
        ]:
            balance_of = vault_contract.functions.balanceOf(
                Web3.to_checksum_address(user_address)
            ).call()
            withdrawal = vault_contract.functions.getUserWithdrawal(
                Web3.to_checksum_address(user_address)
            ).call()
            price_per_share = vault_contract.functions.pricePerShare().call() / 10**6
            withdraw_amount = withdrawal[4] / 10**6
            position.total_balance = balance_of * price_per_share + withdraw_amount

        else:
            total_balance += position.total_balance * currency_price

        # encode datetime
        position.trade_start_date = custom_encoder(pos.trade_start_date)
        position.next_close_round_date = custom_encoder(vault.next_close_round_date)

        positions.append(position)

    total_pnl = sum(position.pnl for position in positions)

    portfolio = schemas.Portfolio(
        total_balance=total_balance, pnl=total_pnl, positions=positions
    )
    return portfolio


@router.get("/{user_address}/total-points", response_model=schemas.PortfolioPoint)
async def get_total_points(session: SessionDep, user_address: str):
    user_points = session.exec(
        select(
            UserPoints.partner_name.label("partner_name"),
            func.sum(UserPoints.points).label("points"),
        )
        .where(UserPoints.wallet_address == user_address.lower())
        .group_by(UserPoints.partner_name)
    ).all()

    points_dict = {}

    for user_point in user_points:
        partner_name = (
            constants.HARMONIX
            if user_point.partner_name in [constants.HARMONIX, constants.HARMONIX_MKT]
            else user_point.partner_name
        )
        if partner_name in points_dict:
            points_dict[partner_name] += user_point.points
        else:
            points_dict[partner_name] = user_point.points

    earned_points = [
        schemas.EarnedPoints(
            name=partner_name,
            point=points,
            created_at=None,
        )
        for partner_name, points in points_dict.items()
    ]

    return schemas.PortfolioPoint(points=earned_points)
