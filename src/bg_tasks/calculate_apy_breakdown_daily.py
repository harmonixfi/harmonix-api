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
from models.vault_apy import VaultAPY, VaultAPYComponent
from models.vault_performance import VaultPerformance
from services import (
    bsx_service,
    camelot_service,
    kelpdao_service,
    lido_service,
    renzo_service,
)

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("calculate_apy_breakdown_daily")

session = Session(engine)

DISTRIBUTE_VAULE: float = 1 / 2
KEYDAO_AEVO_VAULE: float = 8 / 100
RENZO_AEVO_VAULE: float = 8 / 100
DELTA_NEUTRAL_AEVO_VAULE: float = 8 / 100
BSX_POINT_VAULE: float = 0.2
OPTION_YIELD_VALUE: float = 5 / 100


def get_vault_performance(vault_id: uuid.UUID) -> VaultPerformance:
    statement = (
        select(VaultPerformance)
        .where(VaultPerformance.vault_id == vault_id)
        .order_by(VaultPerformance.datetime.desc())
    )
    performance = session.exec(statement).first()
    return performance


def update_or_create_component(vault_apy_id, component_name, component_apy):
    component = session.exec(
        select(VaultAPYComponent).where(
            VaultAPYComponent.vault_apy_id == vault_apy_id,
            VaultAPYComponent.component_name == component_name,
        )
    ).first()

    if component:
        component.component_apy = component_apy
    else:
        new_component = VaultAPYComponent(
            vault_apy_id=vault_apy_id,
            component_name=component_name,
            component_apy=component_apy,
        )
        session.add(new_component)


def upsert_vault_apy(vault_id: uuid.UUID, total_apy: float) -> VaultAPY:
    vault_apy = session.exec(
        select(VaultAPY).where(VaultAPY.vault_id == vault_id)
    ).first()

    if not vault_apy:
        vault_apy = VaultAPY(vault_id=vault_id)

    vault_apy.total_apy = total_apy
    session.add(vault_apy)
    session.commit()

    return vault_apy


def calculate_funding_fees(current_apy, rs_eth_value, ae_usd_value):
    return current_apy - rs_eth_value - ae_usd_value


def save_vault_apy_components(
    vault_id: uuid.UUID, current_apy: float, component_values: dict
):
    vault_apy = upsert_vault_apy(vault_id, current_apy)
    for component_name, component_apy in component_values.items():
        update_or_create_component(vault_apy.id, component_name, component_apy)

    session.commit()


def save_kelpdao_components(
    vault_id: uuid.UUID, current_apy: float, rs_eth_value: float, ae_usd_value: float
):

    component_values = {
        APYComponent.RS_ETH: rs_eth_value,
        APYComponent.AE_USD: ae_usd_value,
        APYComponent.FUNDING_FEES: calculate_funding_fees(
            current_apy, rs_eth_value, ae_usd_value
        ),
    }
    save_vault_apy_components(vault_id, current_apy, component_values)


def save_renzo_components(
    vault_id: uuid.UUID, current_apy: float, ez_eth_value: float, ae_usd_value: float
):
    component_values = {
        APYComponent.EZ_ETH: ez_eth_value,
        APYComponent.AE_USD: ae_usd_value,
        APYComponent.FUNDING_FEES: calculate_funding_fees(
            current_apy, ez_eth_value, ae_usd_value
        ),
    }
    save_vault_apy_components(vault_id, current_apy, component_values)


def save_delta_neutral_components(
    vault_id: uuid.UUID, current_apy: float, wst_eth_value: float, ae_usd_value: float
):
    component_values = {
        APYComponent.WST_ETH: wst_eth_value,
        APYComponent.AE_USD: ae_usd_value,
        APYComponent.FUNDING_FEES: calculate_funding_fees(
            current_apy, wst_eth_value, ae_usd_value
        ),
    }
    save_vault_apy_components(vault_id, current_apy, component_values)


def save_bsx_components(
    vault_id: uuid.UUID,
    current_apy: float,
    wst_eth_value: float,
    bsx_point_value: float,
):
    component_values = {
        APYComponent.WST_ETH: wst_eth_value,
        APYComponent.BSX_POINT: bsx_point_value,
        APYComponent.FUNDING_FEES: calculate_funding_fees(
            current_apy, wst_eth_value, bsx_point_value
        ),
    }
    save_vault_apy_components(vault_id, current_apy, component_values)


def save_option_wheel_components(
    vault_id: uuid.UUID,
    current_apy: float,
    wst_eth_value: float,
    usde_usdc_value: float,
    option_yield_vaule: float,
):
    component_values = {
        APYComponent.WST_ETH: wst_eth_value,
        APYComponent.USDCe_USDC: usde_usdc_value,
        APYComponent.OPTIONS_YIELD: option_yield_vaule,
        APYComponent.ETH_GAINS: current_apy
        - wst_eth_value
        - usde_usdc_value
        - option_yield_vaule,
    }
    save_vault_apy_components(vault_id, current_apy, component_values)


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
                    constants.KELPDAO_VAULT_SLUG,
                    constants.KELPDAO_VAULT_ARBITRUM_SLUG,
                ]:
                    rs_eth_value = kelpdao_service.get_apy() * DISTRIBUTE_VAULE
                    ae_usd_value = KEYDAO_AEVO_VAULE * DISTRIBUTE_VAULE
                    save_kelpdao_components(
                        vault.id, current_apy, rs_eth_value, ae_usd_value
                    )

                elif vault.slug == constants.RENZO_VAULT_SLUG:
                    ez_eth_value = renzo_service.get_apy() * DISTRIBUTE_VAULE
                    ae_usd_value = RENZO_AEVO_VAULE * DISTRIBUTE_VAULE
                    save_renzo_components(
                        vault.id, current_apy, ez_eth_value, ae_usd_value
                    )

                elif vault.slug == constants.DELTA_NEUTRAL_VAULT_VAULT_SLUG:
                    wst_eth_value = lido_service.get_apy() * DISTRIBUTE_VAULE
                    ae_usd_value = DELTA_NEUTRAL_AEVO_VAULE * DISTRIBUTE_VAULE
                    save_delta_neutral_components(
                        vault.id, current_apy, wst_eth_value, ae_usd_value
                    )

                elif vault.slug == constants.OPTIONS_WHEEL_VAULT_VAULT_SLUG:
                    wst_eth_value = camelot_service.get_apy()
                    usde_usdc_value = camelot_service.get_apy_usdc()
                    option_yield_value = OPTION_YIELD_VALUE
                    ae_usd_value = DELTA_NEUTRAL_AEVO_VAULE * DISTRIBUTE_VAULE
                    save_option_wheel_components(
                        vault.id,
                        current_apy,
                        wst_eth_value,
                        usde_usdc_value,
                        option_yield_value,
                    )

                elif vault.slug == constants.BSX_VAULT_SLUG:
                    wst_eth_value = lido_service.get_apy() * DISTRIBUTE_VAULE
                    bsx_point_value = bsx_service.get_points_earned() * BSX_POINT_VAULE
                    save_bsx_components(
                        vault.id, current_apy, wst_eth_value, bsx_point_value
                    )

                elif vault.slug == constants.SOLV_VAULT_SLUG:
                    upsert_vault_apy(vault.id, current_apy)

                elif vault.slug == constants.PENDLE_VAULT_VAULT_SLUG:
                    upsert_vault_apy(vault.id, current_apy)
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
