import logging
import uuid

from sqlmodel import Session, select
from web3 import Web3
from web3.contract import Contract

from core.db import engine
from models import Vault
from core.abi_reader import read_abi
from core import constants

# Initialize logger
logger = logging.getLogger("update_vault_tvl")
logger.setLevel(logging.INFO)

session = Session(engine)
token_abi = read_abi("ERC20")


def get_current_tvl(vault_contract: Contract):
    tvl = vault_contract.functions.totalValueLocked().call()
    return tvl / 1e6  # Adjust as needed based on your contract's TVL unit


def update_tvl(vault_id: uuid.UUID, current_tvl: float):
    vault = session.exec(select(Vault).where(Vault.id == vault_id)).first()
    if vault:
        vault.tvl = current_tvl
        session.commit()


def get_vault_contract(vault: Vault) -> tuple[Contract, Web3]:
    w3 = Web3(Web3.HTTPProvider(constants.NETWORK_RPC_URLS[vault.network_chain]))

    rockonyx_delta_neutral_vault_abi = read_abi("RockOnyxDeltaNeutralVault")
    vault_contract = w3.eth.contract(
        address=vault.contract_address,
        abi=rockonyx_delta_neutral_vault_abi,
    )
    return vault_contract, w3


# Main Execution
def main():
    try:
        # Get the vaults from the Vault table
        vaults = session.exec(
            select(Vault)
            .where(Vault.is_active == True)
        ).all()

        for vault in vaults:
            vault_contract, _ = get_vault_contract(vault)
            current_tvl = get_current_tvl(vault_contract)
            update_tvl(vault.id, current_tvl)
            logger.info(f"Updated TVL for Vault {vault.name} to {current_tvl}")

    except Exception as e:
        logger.error(
            "An error occurred while updating TVL: %s",
            e,
            exc_info=True,
        )


if __name__ == "__main__":
    main()
