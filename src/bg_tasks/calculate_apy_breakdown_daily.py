from datetime import datetime, timedelta, timezone
import logging
from typing import Optional, Tuple, Dict, Any
import uuid

from sqlalchemy import func
from sqlmodel import Session, select
from web3 import Web3
from web3.contract import Contract

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

# Constants
ALLOCATION_RATIO: float = 1 / 2
AEUSD_VAULT_APY: float = 6.5
RENZO_AEVO_VAULE: float = 6.5
BSX_POINT_VAULE: float = 0.2
OPTION_YIELD_VALUE: float = 5

WEEKS_IN_YEAR = 52
DAYS_IN_YEAR: float = 365.25
PERIOD_30_DAYS: int = 30
PERIOD_15_DAYS: int = 15
PERIOD_45_DAYS: int = 45


class VaultAPYCalculator:
    def __init__(self, vault: Vault):
        self.vault = vault
        self.vault_id = vault.id
        self.current_apy = 0
        self.apy_15d = 0
        self.apy_45d = 0

    def calculate_apy_components(self):
        logger.info(
            f"Starting APY calculation for vault: {self.vault.name} (ID: {self.vault_id})"
        )
        self.current_apy, self.apy_15d, self.apy_45d = self._get_vault_apy()
        self.apy_15d = self.apy_15d or 0
        self.apy_45d = self.apy_45d or 0

        handlers = {
            constants.KELPDAO_VAULT_ARBITRUM_SLUG: self._handle_kelpdao_arb,
            constants.KELPDAO_VAULT_SLUG: self._handle_kelpdao,
            constants.RENZO_VAULT_SLUG: self._handle_renzo,
            constants.DELTA_NEUTRAL_VAULT_VAULT_SLUG: self._handle_delta_neutral,
            constants.SOLV_VAULT_SLUG: self._handle_solv,
            constants.KELPDAO_GAIN_VAULT_SLUG: self._handle_kelp_gain,
            constants.ETH_WITH_LENDING_BOOST_YIELD: self._handle_rethink,
            constants.HYPE_DELTA_NEUTRAL_SLUG: self._handle_hype,
        }

        if self.vault.strategy_name == constants.PENDLE_HEDGING_STRATEGY:
            logger.info(
                f"Processing Pendle hedging strategy for vault: {self.vault.name} (slug: {self.vault.slug})"
            )
            self._handle_pendle_hedging_strategy()
        elif self.vault.slug in handlers:
            logger.info(
                f"Processing {self.vault.slug} strategy for vault: {self.vault.name} (slug: {self.vault.slug})"
            )
            handlers[self.vault.slug]()
        else:
            logger.warning(
                f"Vault {self.vault.name} not supported (slug: {self.vault.slug})"
            )

        logger.info(
            f"Completed APY calculation for vault: {self.vault.name} (slug: {self.vault.slug})"
        )

    def _get_vault_apy(self) -> Tuple[float, float, float]:
        if self.vault.strategy_name == constants.OPTIONS_WHEEL_STRATEGY:
            return self.vault.ytd_apy, self.vault.apy_15d, self.vault.apy_45d
        return self.vault.monthly_apy, self.vault.apy_15d, self.vault.apy_45d

    def _handle_kelpdao_arb(self):
        yearly_apy = kelpdao_service.get_apy()
        allocated_apy = yearly_apy * ALLOCATION_RATIO

        handle_kelpdao_arb(
            self.vault_id, self.current_apy, allocated_apy, PERIOD_30_DAYS
        )
        handle_kelpdao_arb(self.vault_id, self.apy_15d, allocated_apy, PERIOD_15_DAYS)
        handle_kelpdao_arb(self.vault_id, self.apy_45d, allocated_apy, PERIOD_45_DAYS)

    def _handle_kelpdao(self):
        rs_eth_value = kelpdao_service.get_apy() * ALLOCATION_RATIO
        ae_usd_value = AEUSD_VAULT_APY * ALLOCATION_RATIO

        handle_kelpdao(
            self.vault_id, self.current_apy, rs_eth_value, ae_usd_value, PERIOD_30_DAYS
        )
        handle_kelpdao(
            self.vault_id, self.apy_15d, rs_eth_value, ae_usd_value, PERIOD_15_DAYS
        )
        handle_kelpdao(
            self.vault_id, self.apy_45d, rs_eth_value, ae_usd_value, PERIOD_45_DAYS
        )

    def _handle_renzo(self):
        ez_eth_value = renzo_service.get_apy() * ALLOCATION_RATIO
        ae_usd_value = RENZO_AEVO_VAULE * ALLOCATION_RATIO

        handle_renzo(
            self.vault_id, self.current_apy, ez_eth_value, ae_usd_value, PERIOD_30_DAYS
        )
        handle_renzo(
            self.vault_id, self.apy_15d, ez_eth_value, ae_usd_value, PERIOD_15_DAYS
        )
        handle_renzo(
            self.vault_id, self.apy_45d, ez_eth_value, ae_usd_value, PERIOD_45_DAYS
        )

    def _handle_delta_neutral(self):
        wst_eth_value = lido_service.get_apy() * ALLOCATION_RATIO * 100
        ae_usd_value = AEUSD_VAULT_APY * ALLOCATION_RATIO

        handle_delta_neutral(
            self.vault_id, self.current_apy, wst_eth_value, ae_usd_value, PERIOD_30_DAYS
        )
        handle_delta_neutral(
            self.vault_id, self.apy_15d, wst_eth_value, ae_usd_value, PERIOD_15_DAYS
        )
        handle_delta_neutral(
            self.vault_id, self.apy_45d, wst_eth_value, ae_usd_value, PERIOD_45_DAYS
        )

    def _handle_solv(self):
        upsert_vault_apy(self.vault_id, self.current_apy, PERIOD_30_DAYS)
        upsert_vault_apy(self.vault_id, self.apy_15d, PERIOD_15_DAYS)
        upsert_vault_apy(self.vault_id, self.apy_45d, PERIOD_45_DAYS)

    def _handle_pendle_hedging_strategy(self):
        pendle_data = pendle_service.get_market(
            constants.CHAIN_IDS["CHAIN_ARBITRUM"], self.vault.pt_address
        )
        pendle_fixed_apy = calculate_fixed_value(pendle_data)

        handle_pendle_hedging_strategy(
            self.vault, self.current_apy, pendle_fixed_apy, PERIOD_30_DAYS
        )
        handle_pendle_hedging_strategy(
            self.vault, self.apy_15d, pendle_fixed_apy, PERIOD_15_DAYS
        )
        handle_pendle_hedging_strategy(
            self.vault, self.apy_45d, pendle_fixed_apy, PERIOD_45_DAYS
        )

    def _handle_kelp_gain(self):
        rs_eth_value = kelpgain_service.get_apy() * ALLOCATION_RATIO
        ae_usd_value = AEUSD_VAULT_APY * ALLOCATION_RATIO

        handle_kelp_gain(
            self.vault_id, self.current_apy, rs_eth_value, ae_usd_value, PERIOD_30_DAYS
        )
        handle_kelp_gain(
            self.vault_id, self.apy_15d, rs_eth_value, ae_usd_value, PERIOD_15_DAYS
        )
        handle_kelp_gain(
            self.vault_id, self.apy_45d, rs_eth_value, ae_usd_value, PERIOD_45_DAYS
        )

    def _handle_rethink(self):
        wst_eth_value = lido_service.get_apy() * 100
        handle_rethink(self.vault_id, self.current_apy, wst_eth_value, PERIOD_30_DAYS)
        handle_rethink(self.vault_id, self.apy_15d, wst_eth_value, PERIOD_15_DAYS)
        handle_rethink(self.vault_id, self.apy_45d, wst_eth_value, PERIOD_45_DAYS)

    def _handle_hype(self):
        vault_performance = get_latest_vault_performance(self.vault_id)
        reward_monthly_apy = (
            vault_performance.reward_monthly_apy
            if vault_performance and vault_performance.reward_monthly_apy is not None
            else 0
        )
        handle_hype(self.vault_id, self.current_apy, reward_monthly_apy, PERIOD_30_DAYS)
        handle_hype(self.vault_id, self.apy_15d, 0, PERIOD_15_DAYS)
        handle_hype(self.vault_id, self.apy_45d, 0, PERIOD_45_DAYS)


# Keep existing utility functions
def calculate_weekly_pnl_in_percentage(profit: float, tvl: float) -> float:
    return profit / tvl


def calculate_annualized_pnl(weekly_pnl_percentage: float, weeks_in_year: int):
    return pow((weekly_pnl_percentage + 1), weeks_in_year) - 1


def calculate_fixed_value(pendle_data: list[PendleMarket]):
    if not pendle_data:
        return 0
    return pendle_data[0].implied_apy * 100 * ALLOCATION_RATIO


def calculate_hyperliquid_value(point_dist, tvl: float, hype_point_usd=5):
    if not point_dist:
        return 0
    weekly_pnl_percentage = calculate_weekly_pnl_in_percentage(
        point_dist.point * hype_point_usd, tvl
    )
    return calculate_annualized_pnl(weekly_pnl_percentage, 12) * 100


# Keep existing database operation functions
def upsert_vault_apy(
    vault_id: uuid.UUID, total_apy: float, period: int
) -> VaultAPYBreakdown:
    vault_apy = session.exec(
        select(VaultAPYBreakdown)
        .where(VaultAPYBreakdown.vault_id == vault_id)
        .where(VaultAPYBreakdown.period == period)
    ).first()

    if not vault_apy:
        vault_apy = VaultAPYBreakdown(vault_id=vault_id)

    vault_apy.total_apy = total_apy
    vault_apy.period = period
    session.add(vault_apy)
    session.commit()

    return vault_apy


def get_latest_hyperliquid_distribution(vault_id):
    return session.exec(
        select(PointDistributionHistory)
        .where(PointDistributionHistory.vault_id == vault_id)
        .where(PointDistributionHistory.partner_name == constants.HYPERLIQUID)
        .order_by(PointDistributionHistory.created_at.desc())
    ).first()


def get_latest_vault_performance(vault_id):
    return session.exec(
        select(VaultPerformance)
        .where(VaultPerformance.vault_id == vault_id)
        .order_by(VaultPerformance.datetime.desc())
    ).first()


# Keep existing handler functions
def handle_pendle_hedging_strategy(
    vault: Vault, apy: float, pendle_fixed_apy: float, period: int
):
    if vault.slug == constants.PENDLE_RSETH_26DEC24_SLUG:
        handle_rseth_dec24_vault(vault, apy, pendle_fixed_apy, period)
    else:
        handle_other_pendle_vaults(vault, apy, pendle_fixed_apy, period)


def handle_rseth_dec24_vault(vault, apy, fixed_value, period: int):
    point_dist = get_latest_hyperliquid_distribution(vault.id)
    hyperliquid_point_value = calculate_hyperliquid_value(point_dist, vault.tvl)

    period_pendle_fixed_apy = 0
    if period in [PERIOD_15_DAYS, PERIOD_45_DAYS]:
        period_pendle_fixed_apy = fixed_value * (period / DAYS_IN_YEAR)

    funding_fee_value = apy - period_pendle_fixed_apy - hyperliquid_point_value

    save_pendle_components(
        vault.id,
        apy,
        period_pendle_fixed_apy,
        hyperliquid_point_value,
        float(funding_fee_value),
        period,
    )


def handle_other_pendle_vaults(vault, apy, fixed_value, period: int):
    vault_performance = get_latest_vault_performance(vault.id)

    period_pendle_fixed_apy = fixed_value
    period_reward_apy = 0

    if period == PERIOD_15_DAYS:
        period_reward_apy = (
            vault_performance.reward_15d_apy
            if vault_performance and vault_performance.reward_15d_apy is not None
            else 0
        )
        period_pendle_fixed_apy = fixed_value * (period / DAYS_IN_YEAR)
    elif period == PERIOD_45_DAYS:
        period_reward_apy = (
            vault_performance.reward_45d_apy
            if vault_performance and vault_performance.reward_45d_apy is not None
            else 0
        )
        period_pendle_fixed_apy = fixed_value * (period / DAYS_IN_YEAR)
    else:
        period_reward_apy = (
            vault_performance.reward_monthly_apy
            if vault_performance and vault_performance.reward_monthly_apy is not None
            else 0
        )

    funding_fee_value = apy - period_pendle_fixed_apy - period_reward_apy
    save_pendle_jun2025_components(
        vault.id, apy, fixed_value, period_reward_apy, float(funding_fee_value), period
    )


# Keep existing handler functions
def handle_kelpdao_arb(vault_id, apy, allocated_apy: float, period: int):
    period_apy = allocated_apy
    if period in [PERIOD_15_DAYS, PERIOD_45_DAYS]:
        period_apy = allocated_apy * (period / DAYS_IN_YEAR)

    funding_fee_value = apy - period_apy
    service = KelpDaoArbitrumApyComponentService(
        vault_id,
        apy,
        period_apy,
        float(funding_fee_value),
        period,
        session,
    )
    service.save()


def handle_kelpdao(
    vault_id, apy, rs_eth_value: float, ae_usd_value: float, period: int
):
    period_rs_eth = rs_eth_value
    period_ae_usd = ae_usd_value
    if period in [PERIOD_15_DAYS, PERIOD_45_DAYS]:
        period_rs_eth = period_rs_eth * (period / DAYS_IN_YEAR)
        period_ae_usd = period_ae_usd * (period / DAYS_IN_YEAR)

    funding_fee_value = apy - period_rs_eth - period_ae_usd
    kelpdao_component_service = KelpDaoApyComponentService(
        vault_id,
        apy,
        period_rs_eth,
        period_ae_usd,
        float(funding_fee_value),
        period,
        session,
    )
    kelpdao_component_service.save()


def handle_renzo(vault_id, apy, ez_eth_value: float, ae_usd_value: float, period: int):
    period_ez_eth = ez_eth_value
    period_ae_usd = ae_usd_value
    if period in [PERIOD_15_DAYS, PERIOD_45_DAYS]:
        period_ez_eth = period_ez_eth * (period / DAYS_IN_YEAR)
        period_ae_usd = period_ae_usd * (period / DAYS_IN_YEAR)

    funding_fee_value = apy - period_ez_eth - period_ae_usd
    renzo_component_service = RenzoApyComponentService(
        vault_id,
        apy,
        period_ez_eth,
        period_ae_usd,
        float(funding_fee_value),
        period,
        session,
    )
    renzo_component_service.save()


def handle_delta_neutral(
    vault_id, apy, wst_eth_value: float, ae_usd_value: float, period: int
):
    period_wst_eth = wst_eth_value
    period_ae_usd = ae_usd_value
    if period in [PERIOD_15_DAYS, PERIOD_45_DAYS]:
        period_wst_eth = period_wst_eth * (period / DAYS_IN_YEAR)
        period_ae_usd = period_ae_usd * (period / DAYS_IN_YEAR)

    funding_fee_value = apy - period_wst_eth - period_ae_usd
    delta_neutral_component_service = DeltaNeutralApyComponentService(
        vault_id,
        apy,
        period_wst_eth,
        period_ae_usd,
        float(funding_fee_value),
        period,
        session,
    )
    delta_neutral_component_service.save()


def handle_kelp_gain(
    vault_id, apy, rs_eth_value: float, ae_usd_value: float, period: int
):
    period_rs_eth = rs_eth_value
    period_ae_usd = ae_usd_value
    if period in [PERIOD_15_DAYS, PERIOD_45_DAYS]:
        period_rs_eth = period_rs_eth * (period / DAYS_IN_YEAR)
        period_ae_usd = period_ae_usd * (period / DAYS_IN_YEAR)

    funding_fee_value = apy - period_rs_eth - period_ae_usd
    kelpdao_component_service = KelpDaoApyComponentService(
        vault_id,
        apy,
        period_rs_eth,
        period_ae_usd,
        float(funding_fee_value),
        period,
        session,
    )
    kelpdao_component_service.save()


def handle_rethink(vault_id, apy, wst_eth_value: float, period: int):
    period_wst_eth = wst_eth_value
    if period in [PERIOD_15_DAYS, PERIOD_45_DAYS]:
        period_wst_eth = period_wst_eth * (period / DAYS_IN_YEAR)

    funding_fee_value = apy - period_wst_eth
    rethink_component_service = RethinkApyComponentService(
        vault_id,
        apy,
        period_wst_eth,
        float(funding_fee_value),
        period,
        session,
    )
    rethink_component_service.save()


def handle_hype(vault_id, apy, period_reward_apy: float, period: int):
    funding_fee_value = apy - period_reward_apy
    hype_component_service = HypeApyComponentService(
        vault_id,
        apy,
        float(period_reward_apy),
        float(funding_fee_value),
        period,
        session,
    )
    hype_component_service.save()


# Keep existing component saving functions
def save_pendle_components(
    vault_id,
    current_apy,
    fixed_value,
    hyperliquid_value,
    funding_fee_value,
    period: int,
):
    pendle_component_service = PendleApyComponentService(
        vault_id,
        current_apy,
        fixed_value,
        hyperliquid_value,
        funding_fee_value,
        period,
        session,
    )
    pendle_component_service.save()


def save_pendle_jun2025_components(
    vault_id,
    current_apy,
    fixed_value,
    reward_monthly_apy,
    funding_fee_value,
    period: int,
):
    service = Pendle26Jun2025ApyComponentService(
        vault_id,
        current_apy,
        fixed_value,
        reward_monthly_apy,
        funding_fee_value,
        period,
        session,
    )
    service.save()


def main():
    try:
        logger.info("Starting APY breakdown calculation for all vaults...")
        vaults = session.exec(select(Vault).where(Vault.is_active == True)).all()
        for vault in vaults:
            try:
                calculator = VaultAPYCalculator(vault)
                calculator.calculate_apy_components()
            except Exception as vault_error:
                logger.error(
                    f"An error occurred while processing vault {vault.name}: {vault_error}",
                    exc_info=True,
                )

        logger.info("Completed APY breakdown calculation for all vaults")

    except Exception as e:
        logger.error(
            "An error occurred during APY breakdown calculation: %s", e, exc_info=True
        )


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file("calculate_apy_breakdown_daily", logger=logger)
    main()
