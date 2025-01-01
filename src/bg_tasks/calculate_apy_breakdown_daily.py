from datetime import datetime, timedelta, timezone
import logging
from typing import Optional
import uuid

from sqlalchemy import func
from sqlmodel import Session, select
from web3 import Web3
from web3.contract import Contract

from bg_tasks.update_delta_neutral_vault_performance_daily import (
    calculate_reward_apy,
)
from core.abi_reader import read_abi
from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models import Vault
from core import constants
from models.point_distribution_history import PointDistributionHistory
from models.reward_distribution_history import RewardDistributionHistory
from models.vault_apy_breakdown import VaultAPYBreakdown
from models.vault_performance import VaultPerformance
from models.vault_reward_history import VaultRewardHistory
from models.vaults import VaultMetadata
from schemas.pendle_market import PendleMarket
from services import (
    bsx_service,
    kelpdao_service,
    lido_service,
    pendle_service,
    renzo_service,
    kelpgain_service,
)
from services.apy_component_service import (
    BSXApyComponentService,
    DeltaNeutralApyComponentService,
    GoldLinkApyComponentService,
    HypeApyComponentService,
    KelpDaoApyComponentService,
    KelpDaoArbitrumApyComponentService,
    OptionWheelApyComponentService,
    Pendle26Jun2025ApyComponentService,
    PendleApyComponentService,
    RenzoApyComponentService,
    RethinkApyComponentService,
)
from services.gold_link_service import get_current_rewards_earned
from services.market_data import get_price

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("calculate_apy_breakdown_daily")

session = Session(engine)

ALLOCATION_RATIO: float = 1 / 2
AEUSD_VAULT_APY: float = 6.5
RENZO_AEVO_VAULE: float = 6.5
BSX_POINT_VAULE: float = 0.2
OPTION_YIELD_VALUE: float = 5

WEEKS_IN_YEAR = 52


def upsert_vault_apy(vault_id: uuid.UUID, total_apy: float) -> VaultAPYBreakdown:
    vault_apy = session.exec(
        select(VaultAPYBreakdown).where(VaultAPYBreakdown.vault_id == vault_id)
    ).first()

    if not vault_apy:
        vault_apy = VaultAPYBreakdown(vault_id=vault_id)

    vault_apy.total_apy = total_apy
    session.add(vault_apy)
    session.commit()

    return vault_apy


def get_vault_performance(vault_id: uuid.UUID) -> VaultPerformance:
    statement = (
        select(VaultPerformance)
        .where(VaultPerformance.vault_id == vault_id)
        .order_by(VaultPerformance.datetime.desc())
    )
    performance = session.exec(statement).first()
    return performance


def calculate_funding_fees(current_apy, rs_eth_value, ae_usd_value) -> float:
    return current_apy - rs_eth_value - ae_usd_value


def calculate_weekly_pnl_in_percentage(profit: float, tvl: float) -> float:
    return profit / tvl


def calculate_annualized_pnl(weekly_pnl_percentage: float, weeks_in_year: int):
    return pow((weekly_pnl_percentage + 1), weeks_in_year) - 1


def _get_vault_apy(vault: Vault) -> float:
    if vault.strategy_name == constants.OPTIONS_WHEEL_STRATEGY:
        return vault.ytd_apy

    return vault.monthly_apy


def handle_pendle_hedging_strategy(vault: Vault, current_apy: float):
    """Handle APY calculations for Pendle Hedging Strategy vaults"""
    pendle_data = pendle_service.get_market(
        constants.CHAIN_IDS["CHAIN_ARBITRUM"], vault.pt_address
    )

    fixed_value = calculate_fixed_value(pendle_data)

    if vault.slug == constants.PENDLE_RSETH_26DEC24_SLUG:
        handle_rseth_dec24_vault(vault, current_apy, fixed_value)
    else:
        handle_other_pendle_vaults(vault, current_apy, fixed_value)


def calculate_fixed_value(pendle_data: list[PendleMarket]):
    """Calculate fixed value component from Pendle data"""
    if not pendle_data:
        return 0
    return pendle_data[0].implied_apy * 100 * ALLOCATION_RATIO


def handle_rseth_dec24_vault(vault, current_apy, fixed_value):
    """Handle RSETH Dec24 vault specific calculations"""
    point_dist = get_latest_hyperliquid_distribution(vault.id)
    hyperliquid_point_value = calculate_hyperliquid_value(point_dist, vault.tvl)
    funding_fee_value = calculate_funding_fees(
        current_apy, fixed_value, hyperliquid_point_value
    )

    save_pendle_components(
        vault.id,
        current_apy,
        fixed_value,
        hyperliquid_point_value,
        float(funding_fee_value),
    )


def handle_other_pendle_vaults(vault, current_apy, fixed_value):
    """Handle calculations for other Pendle vaults"""
    vault_performance = get_latest_vault_performance(vault.id)
    reward_monthly_apy = (
        vault_performance.reward_monthly_apy
        if vault_performance and vault_performance.reward_monthly_apy is not None
        else 0
    )
    funding_fee_value = current_apy - fixed_value - reward_monthly_apy
    save_pendle_jun2025_components(
        vault.id, current_apy, fixed_value, reward_monthly_apy, float(funding_fee_value)
    )


def get_latest_hyperliquid_distribution(vault_id):
    """Get the latest Hyperliquid point distribution"""
    return session.exec(
        select(PointDistributionHistory)
        .where(PointDistributionHistory.vault_id == vault_id)
        .where(PointDistributionHistory.partner_name == constants.HYPERLIQUID)
        .order_by(PointDistributionHistory.created_at.desc())
    ).first()


def calculate_hyperliquid_value(point_dist, tvl: float, hype_point_usd=5):
    """Calculate Hyperliquid point value"""
    if not point_dist:
        return 0

    weekly_pnl_percentage = calculate_weekly_pnl_in_percentage(
        point_dist.point * hype_point_usd, tvl
    )
    return calculate_annualized_pnl(weekly_pnl_percentage, 12) * 100


def get_latest_vault_performance(vault_id):
    """Get latest vault performance data"""
    return session.exec(
        select(VaultPerformance)
        .where(VaultPerformance.vault_id == vault_id)
        .order_by(VaultPerformance.datetime.desc())
    ).first()


def save_pendle_components(
    vault_id, current_apy, fixed_value, hyperliquid_value, funding_fee_value
):
    """Save Pendle APY components"""
    pendle_component_service = PendleApyComponentService(
        vault_id,
        current_apy,
        fixed_value,
        hyperliquid_value,
        funding_fee_value,
        session,
    )
    pendle_component_service.save()


def save_pendle_jun2025_components(
    vault_id, current_apy, fixed_value, reward_monthly_apy, funding_fee_value
):
    """Save Pendle June 2025 APY components"""
    service = Pendle26Jun2025ApyComponentService(
        vault_id,
        current_apy,
        fixed_value,
        reward_monthly_apy,
        funding_fee_value,
        session,
    )
    service.save()


# Main Execution
def main():
    try:
        logger.info("Start calculating APY breakdown daily for vaults...")
        vaults = session.exec(select(Vault).where(Vault.is_active == True)).all()

        for vault in vaults:
            try:
                current_apy = _get_vault_apy(vault)

                if vault.slug == constants.KELPDAO_VAULT_ARBITRUM_SLUG:
                    rs_eth_value = kelpdao_service.get_apy() * ALLOCATION_RATIO
                    funding_fee_value = current_apy - rs_eth_value
                    kelpdao_arb_component_service = KelpDaoArbitrumApyComponentService(
                        vault.id,
                        current_apy,
                        rs_eth_value,
                        float(funding_fee_value),
                        session,
                    )
                    kelpdao_arb_component_service.save()

                if vault.slug == constants.KELPDAO_VAULT_SLUG:
                    rs_eth_value = kelpdao_service.get_apy() * ALLOCATION_RATIO

                    ae_usd_value = AEUSD_VAULT_APY * ALLOCATION_RATIO
                    funding_fee_value = calculate_funding_fees(
                        current_apy, rs_eth_value, ae_usd_value
                    )
                    kelpdao_component_service = KelpDaoApyComponentService(
                        vault.id,
                        current_apy,
                        rs_eth_value,
                        ae_usd_value,
                        float(funding_fee_value),
                        session,
                    )
                    kelpdao_component_service.save()

                elif vault.slug == constants.RENZO_VAULT_SLUG:
                    ez_eth_value = renzo_service.get_apy() * ALLOCATION_RATIO
                    ae_usd_value = RENZO_AEVO_VAULE * ALLOCATION_RATIO
                    funding_fee_value = calculate_funding_fees(
                        current_apy, ez_eth_value, ae_usd_value
                    )

                    renzo_component_service = RenzoApyComponentService(
                        vault.id,
                        current_apy,
                        ez_eth_value,
                        ae_usd_value,
                        float(funding_fee_value),
                        session,
                    )
                    renzo_component_service.save()

                elif vault.slug == constants.DELTA_NEUTRAL_VAULT_VAULT_SLUG:
                    wst_eth_value = lido_service.get_apy() * ALLOCATION_RATIO * 100
                    ae_usd_value = AEUSD_VAULT_APY * ALLOCATION_RATIO
                    funding_fee_value = calculate_funding_fees(
                        current_apy, wst_eth_value, ae_usd_value
                    )
                    delta_neutral_component_service = DeltaNeutralApyComponentService(
                        vault.id,
                        current_apy,
                        wst_eth_value,
                        ae_usd_value,
                        float(funding_fee_value),
                        session,
                    )
                    delta_neutral_component_service.save()

                # elif vault.slug == constants.OPTIONS_WHEEL_VAULT_VAULT_SLUG:
                #     wst_eth_value = (
                #         camelot_service.get_pool_apy(
                #             constants.CAMELOT_LP_POOL["WST_ETH_ADDRESS"]
                #         )
                #         * 0.6
                #     )
                #     usde_usdc_value = (
                #         camelot_service.get_pool_apy(
                #             constants.CAMELOT_LP_POOL["USDE_USDC_ADDRESS"]
                #         )
                #         * 0.2
                #     )
                #     option_yield_value = OPTION_YIELD_VALUE
                #     ae_usd_value = AEUSD_VAULT_APY * ALLOCATION_RATIO
                #     eth_gains_value = (
                #         current_apy
                #         - wst_eth_value
                #         - usde_usdc_value
                #         - option_yield_value
                #     )

                #     option_wheel_component_service = OptionWheelApyComponentService(
                #         vault.id,
                #         current_apy,
                #         wst_eth_value,
                #         usde_usdc_value,
                #         option_yield_value,
                #         eth_gains_value,
                #         session,
                #     )
                #     option_wheel_component_service.save()

                elif vault.slug == constants.BSX_VAULT_SLUG:
                    wst_eth_value = lido_service.get_apy() * ALLOCATION_RATIO * 100
                    last_tuesday = datetime.now(timezone.utc) - timedelta(
                        days=datetime.now(timezone.utc).weekday() + 6
                    )
                    point_dist_hist = session.exec(
                        select(PointDistributionHistory)
                        .where(PointDistributionHistory.vault_id == vault.id)
                        .where(PointDistributionHistory.partner_name == constants.BSX)
                        .where(
                            func.date(PointDistributionHistory.created_at)
                            == last_tuesday.date()
                        )
                        .order_by(PointDistributionHistory.created_at.desc())
                    ).first()

                    bsx_point = bsx_service.get_points_earned()
                    if point_dist_hist:
                        bsx_point = bsx_point - float(point_dist_hist.point)

                    bsx_point_value = 0
                    if bsx_point >= 0:
                        bsx_point_value = bsx_point * BSX_POINT_VAULE

                    # bsx_point_value = float(102) * BSX_POINT_VAULE
                    # Calculate weekly PnL in percentage
                    weekly_pnl_percentage = calculate_weekly_pnl_in_percentage(
                        bsx_point_value, vault.tvl
                    )
                    # Calculate annualized PnL based on weekly PnL
                    annualized_point_pnl = (
                        calculate_annualized_pnl(weekly_pnl_percentage, WEEKS_IN_YEAR)
                        * 100
                    )
                    funding_fee_value = calculate_funding_fees(
                        current_apy, wst_eth_value, annualized_point_pnl
                    )

                    bsx_component_service = BSXApyComponentService(
                        vault.id,
                        current_apy,
                        wst_eth_value,
                        float(annualized_point_pnl),
                        float(funding_fee_value),
                        session,
                    )
                    bsx_component_service.save()
                elif vault.slug == constants.SOLV_VAULT_SLUG:
                    upsert_vault_apy(vault.id, current_apy)

                elif vault.strategy_name == constants.PENDLE_HEDGING_STRATEGY:
                    handle_pendle_hedging_strategy(vault, current_apy)

                elif vault.slug in [constants.KELPDAO_GAIN_VAULT_SLUG]:
                    rs_eth_value = kelpgain_service.get_apy() * ALLOCATION_RATIO

                    ae_usd_value = AEUSD_VAULT_APY * ALLOCATION_RATIO
                    funding_fee_value = calculate_funding_fees(
                        current_apy, rs_eth_value, ae_usd_value
                    )
                    kelpdao_component_service = KelpDaoApyComponentService(
                        vault.id,
                        current_apy,
                        rs_eth_value,
                        ae_usd_value,
                        float(funding_fee_value),
                        session,
                    )
                    kelpdao_component_service.save()

                elif vault.slug == constants.GOLD_LINK_SLUG:
                    rewards_hist = session.exec(
                        select(VaultRewardHistory)
                        .where(VaultRewardHistory.vault_id == vault.id)
                        .order_by(VaultRewardHistory.datetime.desc())
                    ).first()

                    vault_metadata = session.exec(
                        select(VaultMetadata).where(VaultMetadata.vault_id == vault.id)
                    ).first()

                    if vault_metadata is None:
                        logger.error(
                            "Breakdown- No vault metadata found for vault %s. Skipping.",
                            vault.id,
                        )  # Log error if None
                        continue

                    rewards_earned = get_current_rewards_earned(
                        vault, vault_metadata.goldlink_trading_account
                    )
                    if rewards_hist:
                        rewards_earned = rewards_earned - float(
                            rewards_hist.earned_rewards
                        )

                    arb_price = get_price("ARBUSDT")
                    rewards_value = 0
                    if rewards_earned >= 0:
                        rewards_value = rewards_earned * arb_price

                    # Calculate weekly PnL in percentage
                    weekly_pnl_percentage = calculate_weekly_pnl_in_percentage(
                        rewards_value, vault.tvl
                    )
                    # Calculate annualized PnL based on weekly PnL
                    annualized_rewards_pnl = (
                        calculate_annualized_pnl(weekly_pnl_percentage, WEEKS_IN_YEAR)
                        * 100
                    )
                    funding_fee_value = current_apy - annualized_rewards_pnl

                    goldlink_component_service = GoldLinkApyComponentService(
                        vault.id,
                        current_apy,
                        float(annualized_rewards_pnl),
                        float(funding_fee_value),
                        session,
                    )
                    goldlink_component_service.save()

                elif vault.slug == constants.ETH_WITH_LENDING_BOOST_YIELD:
                    wst_eth_value = lido_service.get_apy() * 100
                    funding_fee_value = current_apy - wst_eth_value

                    rethink_component_service = RethinkApyComponentService(
                        vault.id,
                        current_apy,
                        wst_eth_value,
                        float(funding_fee_value),
                        session,
                    )
                    rethink_component_service.save()

                elif vault.slug == constants.HYPE_DELTA_NEUTRAL_SLUG:
                    # Calculate the monthly APY for the vault based on its ID and TVL
                    vault_performance = session.exec(
                        select(VaultPerformance)
                        .where(VaultPerformance.vault_id == vault.id)
                        .order_by(VaultPerformance.datetime.desc())
                    ).first()
                    reward_monthly_apy = (
                        vault_performance.reward_monthly_apy
                        if vault_performance
                        and vault_performance.reward_monthly_apy is not None
                        else 0
                    )

                    funding_fee_value = current_apy - reward_monthly_apy
                    hype_component_service = HypeApyComponentService(
                        vault.id,
                        current_apy,
                        float(reward_monthly_apy),
                        float(funding_fee_value),
                        session,
                    )
                    hype_component_service.save()

                else:
                    logger.warning(f"Vault {vault.name} not supported")

            except Exception as vault_error:
                logger.error(
                    f"An error occurred while processing vault {vault.name}: {vault_error}",
                    exc_info=True,
                )

    except Exception as e:
        logger.error(
            "An error occurred during APY breakdown calculation: %s", e, exc_info=True
        )


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file("calculate_apy_breakdown_daily", logger=logger)
    main()
