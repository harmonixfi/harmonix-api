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
from services.vault_contract_service import VaultContractService
from utils.web3_utils import (
    get_current_tvl,
    get_user_state_by_block_number,
    get_vault_contract,
)
from hexbytes import HexBytes

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("update_vault_tvl")

session = Session(engine)


# fake event by link https://arbiscan.io/tx/0xcbbfd451b0426954ebc54f21e63338b427d43db2e70db930a0e2aedce2ff6942
def event_data():
    return {
        "removed": False,
        "logIndex": 1,
        "transactionIndex": 0,
        "transactionHash": "0xcbbfd451b0426954ebc54f21e63338b427d43db2e70db930a0e2aedce2ff6942",
        "blockHash": "0x4874e743d6e778c5b4af1c0547f7bf5f8d6bcfae8541022d9b1959ce7d41da9f",
        "blockNumber": 286690866,
        "address": "0x4a10C31b642866d3A3Df2268cEcD2c5B14600523",
        "data": HexBytes(
            "0x0000000000000000000000000000000000000000000000000000000001312d000000000000000000000000000000000000000000000000000000000001312d00"
        ),
        "topics": [
            HexBytes(
                "0x73a19dd210f1a7f902193214c0ee91dd35ee5b4d920cba8d519eca65a7b488ca"
            ),
            HexBytes(
                "0x00000000000000000000000020f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7"
            ),
        ],
    }


def _extract_block_number_from_event(entry) -> int:
    return int(entry["blockNumber"] or 0)


# Main Execution
def main():
    try:
        # Get the vaults from the Vault table
        entry = event_data()
        vault = session.exec(
            select(Vault).where(Vault.id == "2e63ed8f-c42a-4ac8-bf31-092270fc9ed1")
        ).first()
        vault_contract_service = VaultContractService()
        abi_name, _ = vault_contract_service.get_vault_abi(vault=vault)

        vault_contract, _ = vault_contract_service.get_vault_contract(
            vault.network_chain, vault.contract_address, abi_name
        )
        pre_block_number = _extract_block_number_from_event(entry=entry) - 1
        user_state = get_user_state_by_block_number(
            vault_contract,
            "0x6F60abAFbE336cDd5035B107c4cDeb95e4FC978b",
            pre_block_number,
        )
        print(user_state)

    except Exception as e:
        print(traceback.print_exc())
        logger.error(
            "An error occurred while updating TVL: %s",
            e,
            exc_info=True,
        )


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file("test_get_user_state_by_block_number", logger=logger)
    main()
