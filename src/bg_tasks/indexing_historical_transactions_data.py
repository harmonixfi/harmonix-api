import logging
from web3 import Web3, HTTPProvider
from sqlmodel import Session
from core.config import settings
from core.db import engine
from models.onchain_transaction_history import OnchainTransactionHistory
from services.arbiscan_service import get_transactions

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Setup Web3 connection
w3 = Web3(HTTPProvider(settings.ARBITRUM_MAINNET_INFURA_URL))


def process_transaction(transaction):
    method_id = transaction["methodId"]
    return {
        "tx_hash": transaction["hash"],
        "block_number": transaction["blockNumber"],
        "timestamp": transaction["timeStamp"],
        "from_address": transaction["from"],
        "to_address": transaction["to"],
        "method_id": method_id,
        "input": transaction["input"],
        "value": w3.from_wei(int(transaction["value"]), "ether"),
    }


def index_transactions(contract_addresses):
    with Session(engine) as session:
        for address, start_block in contract_addresses:
            page = 1
            while True:
                transactions = get_transactions(
                    address, start_block, 99999999, page, offset=100
                )
                if not transactions:
                    break

                for tx in transactions:
                    tx_data = process_transaction(tx)
                    new_transaction = OnchainTransactionHistory(**tx_data)
                    session.add(new_transaction)
                session.commit()
                page += 1


if __name__ == "__main__":
    contract_addresses = [
        (
            Web3.to_checksum_address("0x2b7cdad36a86fd05ac1680cdc42a0ea16804d80c"),
            0,
        ),
        (
            Web3.to_checksum_address("0x4a10C31b642866d3A3Df2268cEcD2c5B14600523"),
            0,
        ),
    ]
    index_transactions(contract_addresses)
