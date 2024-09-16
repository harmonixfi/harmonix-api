import logging
import uuid

from sqlmodel import Session, select
from web3 import Web3
from web3.contract import Contract

from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models import Vault
from core.abi_reader import read_abi
from core import constants
from models.apy_component import APYComponent
from models.vault_apy_breakdown import VaultAPYBreakdown, VaultAPYComponent
from models.vault_performance import VaultPerformance
from services import (
    bsx_service,
    camelot_service,
    kelpdao_service,
    lido_service,
    pendle_service,
    renzo_service,
)
from services.apy_component_service import (
    BSXComponentService,
    DeltaNeutralComponentService,
    KelpDaoComponentService,
    OptionWheelComponentService,
    PendleComponentService,
    RenzoComponentService,
)

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("calculate_apy_breakdown_daily")

session = Session(engine)

ALLOCATION_RATIO: float = 1 / 2
AEUSD_VAULT_APY: float = 8 / 100
RENZO_AEVO_VAULE: float = 8 / 100
BSX_POINT_VAULE: float = 0.2
OPTION_YIELD_VALUE: float = 5 / 100

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


def calculate_funding_fees(current_apy, rs_eth_value, ae_usd_value):
    return current_apy - rs_eth_value - ae_usd_value


def calculate_weekly_pnl_in_percentage(profit: float, tvl: float) -> float:
    return profit / tvl


def calculate_annualized_pnl(weekly_pnl_percentage: float, weeks_in_year: int):
    return pow((weekly_pnl_percentage + 1), weeks_in_year) - 1


# Main Execution
def main():
    try:
        logger.info("Start calculating APY breakdown daily for vaults...")
        vaults = session.exec(select(Vault).where(Vault.is_active == True)).all()

        for vault in vaults:
            try:
                performance = get_vault_performance(vault.id)
                current_apy = (
                    performance.apy_ytd
                    if vault.strategy_name == constants.OPTIONS_WHEEL_STRATEGY
                    else performance.apy_1m
                )

                if vault.slug in [
                    constants.KEYDAO_VAULT_SLUG,
                    constants.KEYDAO_VAULT_ARBITRUM_SLUG,
                ]:
                    rs_eth_value = kelpdao_service.get_apy() * ALLOCATION_RATIO
                    ae_usd_value = AEUSD_VAULT_APY * ALLOCATION_RATIO
                    funding_fee_value = calculate_funding_fees(
                        current_apy, rs_eth_value, ae_usd_value
                    )
                    kelpdao_component_service = KelpDaoComponentService(
                        vault.id,
                        current_apy,
                        rs_eth_value,
                        ae_usd_value,
                        funding_fee_value,
                        session,
                    )
                    kelpdao_component_service.save()

                elif vault.slug == constants.RENZO_VAULT_SLUG:
                    ez_eth_value = renzo_service.get_apy() * ALLOCATION_RATIO
                    ae_usd_value = RENZO_AEVO_VAULE * ALLOCATION_RATIO
                    funding_fee_value = calculate_funding_fees(
                        current_apy, ez_eth_value, ae_usd_value
                    )

                    renzo__component_service = RenzoComponentService(
                        vault.id,
                        current_apy,
                        ez_eth_value,
                        ae_usd_value,
                        funding_fee_value,
                        session,
                    )
                    renzo__component_service.save()

                elif vault.slug == constants.DELTA_NEUTRAL_VAULT_VAULT_SLUG:
                    wst_eth_value = lido_service.get_apy() * ALLOCATION_RATIO
                    ae_usd_value = AEUSD_VAULT_APY * ALLOCATION_RATIO
                    funding_fee_value = calculate_funding_fees(
                        current_apy, wst_eth_value, ae_usd_value
                    )
                    delta_neutral_component_service = DeltaNeutralComponentService(
                        vault.id,
                        current_apy,
                        wst_eth_value,
                        ae_usd_value,
                        funding_fee_value,
                        session,
                    )
                    delta_neutral_component_service.save()

                elif vault.slug == constants.OPTIONS_WHEEL_VAULT_VAULT_SLUG:
                    wst_eth_value = camelot_service.get_pool_apy(
                        constants.CAMELOT_LP_POOL["WST_ETH_ADDRESS"]
                    )
                    usde_usdc_value = camelot_service.get_pool_apy(
                        constants.CAMELOT_LP_POOL["USDE_USDC_ADDRESS"]
                    )
                    option_yield_value = OPTION_YIELD_VALUE
                    ae_usd_value = AEUSD_VAULT_APY * ALLOCATION_RATIO
                    eth_gains_value = (
                        current_apy
                        - wst_eth_value
                        - usde_usdc_value
                        - option_yield_value
                    )

                    option_wheel_component_service = OptionWheelComponentService(
                        vault.id,
                        current_apy,
                        wst_eth_value,
                        usde_usdc_value,
                        option_yield_value,
                        eth_gains_value,
                        session,
                    )
                    option_wheel_component_service.save()

                elif vault.slug == constants.BSX_VAULT_SLUG:
                    wst_eth_value = lido_service.get_apy() * ALLOCATION_RATIO
                    bsx_point_value = bsx_service.get_points_earned() * BSX_POINT_VAULE
                    # Calculate weekly PnL in percentage
                    weekly_pnl_percentage = calculate_weekly_pnl_in_percentage(
                        bsx_point_value, vault.tvl
                    )
                    # Calculate annualized PnL based on weekly PnL
                    annualized_pnl = calculate_annualized_pnl(
                        weekly_pnl_percentage, WEEKS_IN_YEAR
                    )
                    funding_fee_value = (
                        calculate_funding_fees(
                            current_apy, wst_eth_value, bsx_point_value
                        ),
                    )
                    bsx_component_service = BSXComponentService(
                        vault.id,
                        current_apy,
                        wst_eth_value,
                        annualized_pnl,
                        funding_fee_value,
                        session,
                    )
                    bsx_component_service.save()
                elif vault.slug == constants.SOLV_VAULT_SLUG:
                    upsert_vault_apy(vault.id, current_apy)

                elif vault.slug == constants.PENDLE_VAULT_VAULT_SLUG:
                    pendle_data = pendle_service.get_market(
                        constants.CHAIN_IDS["CHAIN_ARBITRUM"], vault.pt_address
                    )
                    fixed_value = 0
                    if pendle_data:
                        fixed_value = pendle_data[0].implied_apy

                    hyperliquid_point_value = 0
                    funding_fee_value = calculate_funding_fees(
                        current_apy, fixed_value, hyperliquid_point_value
                    )
                    pendle_component_service = PendleComponentService(
                        vault.id,
                        current_apy,
                        fixed_value,
                        hyperliquid_point_value,
                        funding_fee_value,
                        session,
                    )
                    pendle_component_service.save()
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
