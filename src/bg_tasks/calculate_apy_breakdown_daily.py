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
from models.vault_apy import VaultAPY
from models.vault_performance import VaultPerformance
from services import kelpdao_service
from utils.web3_utils import get_current_tvl, get_vault_contract

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("calculate_apy_breakdown_daily")

session = Session(engine)

DISTRIBUTE_VAULE: float = 1 / 2
KEYDAO_AEVO_VAULE: float = 8 / 100


def get_vault_performance(vault_id: uuid.UUID) -> VaultPerformance:
    statement = (
        select(VaultPerformance)
        .where(VaultPerformance.vault_id == vault_id)
        .order_by(VaultPerformance.datetime.desc())
    )
    performance = session.exec(statement).first()
    return performance


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


# Main Execution
def main():
    try:
        logger.info("Start calculate apy breakdown daily for vaults...")
        # Get the vaults from the Vault table
        vaults = session.exec(select(Vault).where(Vault.is_active == True)).all()

        for vault in vaults:
            if vault.slug == constants.KELPDAO_VAULT_SLUG:
                rs_eth_value = kelpdao_service.get_apy() * DISTRIBUTE_VAULE
                ae_usd_value = KEYDAO_AEVO_VAULE * DISTRIBUTE_VAULE

                performance = get_vault_performance(vault.id)
                current_apy = (
                    performance.apy_ytd
                    if vault.strategy_name == constants.OPTIONS_WHEEL_STRATEGY
                    else performance.apy_1m
                )
                funding_fees_value = current_apy - rs_eth_value - ae_usd_value
                data = upsert_vault_apy(vault.id, current_apy)
                print(data)

            elif vault.strategy_name == constants.DELTA_NEUTRAL_STRATEGY:
                abi = "RockOnyxDeltaNeutralVault"
            elif vault.strategy_name == constants.OPTIONS_WHEEL_STRATEGY:
                abi = "rockonyxstablecoin"
            elif vault.strategy_name == constants.PENDLE_HEDGING_STRATEGY:
                abi = "pendlehedging"
            else:
                # raise ValueError("Not support vault")
                ab = ""

            # logger.info(f"Updated TVL for Vault {vault.name} to {current_tvl}")

    except Exception as e:
        logger.error(
            "An error occurred while updating TVL: %s",
            e,
            exc_info=True,
        )


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file("calculate_apy_breakdown_daily", logger=logger)
    main()
