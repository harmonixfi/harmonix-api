import logging
import traceback
import uuid

from sqlmodel import Session, select
from web3 import Web3
from web3.contract import Contract

from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models import Vault
from core.abi_reader import read_abi
from core import constants
from utils.web3_utils import get_current_tvl, get_vault_contract

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("update_vault_tvl")

session = Session(engine)
token_abi = read_abi("ERC20")


def update_tvl(vault_id: uuid.UUID, current_tvl: float):
    vault = session.exec(select(Vault).where(Vault.id == vault_id)).first()
    if vault:
        vault.tvl = current_tvl
        session.commit()


# Main Execution
def main():
    try:
        logger.info("Start updating TVL for vaults...")
        # Get the vaults from the Vault table
        vaults = session.exec(select(Vault).where(Vault.is_active == True)).all()

        for vault in vaults:
            decimals = 1e6
            if vault.slug == constants.ETH_WITH_LENDING_BOOST_YIELD:
                abi = "rethink_yield_v2"
            if vault.slug == constants.SOLV_VAULT_SLUG:
                abi = "solv"
                decimals = 1e8
            elif vault.slug == constants.GOLD_LINK_SLUG:
                abi = "goldlink"
            elif (
                vault.strategy_name == constants.DELTA_NEUTRAL_STRATEGY
                and vault.slug != constants.GOLD_LINK_SLUG
            ):
                abi = "RockOnyxDeltaNeutralVault"
            elif vault.strategy_name == constants.OPTIONS_WHEEL_STRATEGY:
                abi = "rockonyxstablecoin"
            elif vault.strategy_name == constants.PENDLE_HEDGING_STRATEGY:
                abi = "pendlehedging"
            else:
                raise ValueError("Not support vault")

            vault_contract, _ = get_vault_contract(vault, abi)
            current_tvl = get_current_tvl(vault_contract, decimals)
            update_tvl(vault.id, current_tvl)
            logger.info(f"Updated TVL for Vault {vault.name} to {current_tvl}")

    except Exception as e:
        print(traceback.print_exc())
        logger.error(
            "An error occurred while updating TVL: %s",
            e,
            exc_info=True,
        )


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file("update_vault_tvl", logger=logger)
    main()
