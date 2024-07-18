import logging
import requests
from web3 import Web3, HTTPProvider
from sqlmodel import SQLModel, create_engine, Session, select
from sqlmodel import Field, Index
from datetime import datetime
from core.config import settings
from core.db import engine
from services.arbiscan_service import get_transactions

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Setup Web3 connection
w3 = Web3(HTTPProvider(settings.ARBITRUM_MAINNET_INFURA_URL))

session = Session(engine)


class Transaction(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    tx_hash: str = Field(index=True)
    block_number: int = Field(index=True)
    from_address: str
    to_address: str
    method_id: str
    input: str
    data: str
    value: float


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
                    address, start_block, w3.eth.block_number, page
                )
                if not transactions:
                    break
                for tx in transactions:
                    tx_data = process_transaction(tx["hash"])
                    new_transaction = Transaction(**tx_data)
                    session.add(new_transaction)
                session.commit()
                page += 1


if __name__ == "__main__":
    contract_addresses = [
        ("0xContractAddress1", 1000000),
        ("0xContractAddress2", 1000000),
    ]
    index_transactions(contract_addresses)
