import logging
import requests
from web3 import Web3, HTTPProvider
from sqlmodel import SQLModel, create_engine, Session, select
from sqlmodel import Field, Index
from datetime import datetime
from core.config import settings
from core.db import engine
from models.onchain_transaction_history import OnchainTransactionHistory
from services.arbiscan_service import get_transactions

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Setup Web3 connection
w3 = Web3(HTTPProvider(settings.ARBITRUM_MAINNET_INFURA_URL))


def process_transaction(tx_hash):
    transaction = w3.eth.get_transaction(tx_hash)
    method_id = transaction.input[:10]
    return {
        "tx_hash": transaction.hash.hex(),
        "block_number": transaction.blockNumber,
        "from_address": transaction["from"],
        "to_address": transaction.to,
        "method_id": method_id,
        "input": transaction.input,
        "data": transaction.input[10:],
        "value": w3.from_wei(transaction.value, "ether"),
    }


def index_transactions(contract_addresses):
    with Session(engine) as session:
        for address, start_block in contract_addresses:
            page = 1
            while True:
                transactions = get_transactions(
                    address, start_block, w3.eth.block_number, page, offset=100
                )
                if not transactions:
                    break

                for tx in transactions:
                    tx_data = process_transaction(tx["hash"])
                    new_transaction = OnchainTransactionHistory(**tx_data)
                    session.add(new_transaction)
                session.commit()
                page += 1


if __name__ == "__main__":
    contract_addresses = [
        (
            Web3.to_checksum_address("0x2b7cdad36a86fd05ac1680cdc42a0ea16804d80c"),
            222059232,
        ),
    ]
    index_transactions(contract_addresses)
