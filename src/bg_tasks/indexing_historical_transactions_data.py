import logging
import sys
import traceback
import click
from web3 import Web3
from sqlmodel import Session, select
from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models.onchain_transaction_history import OnchainTransactionHistory
from models.vaults import NetworkChain
from services import arbiscan_service, etherscan_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_BLOCK_NUMBER = 9999999999


def process_transaction(transaction, chain: NetworkChain):
    method_id = transaction["methodId"]
    return {
        "tx_hash": transaction["hash"],
        "block_number": transaction["blockNumber"],
        "timestamp": transaction["timeStamp"],
        "from_address": transaction["from"],
        "to_address": transaction["to"],
        "method_id": method_id,
        "input": transaction["input"],
        "value": Web3.from_wei(int(transaction["value"]), "ether"),
        "chain": chain.value,
    }


def get_latest_block(session: Session, address: str, chain: NetworkChain):
    latest_block_record = session.exec(
        select(OnchainTransactionHistory)
        .where(OnchainTransactionHistory.to_address == address.lower())
        .where(OnchainTransactionHistory.chain == chain.value)
        .order_by(OnchainTransactionHistory.block_number.desc())
    ).first()

    if latest_block_record:
        return latest_block_record.block_number
    else:
        return 0


def index_transactions(contract_addresses, chain: NetworkChain):
    try:
        logger.info("Start indexing transaction %s %s", contract_addresses, chain)

        if chain == NetworkChain.arbitrum_one:
            get_transactions = arbiscan_service.get_transactions
        elif chain == NetworkChain.ethereum:
            get_transactions = etherscan_service.get_transactions
        else:
            raise ValueError("Chain not supported")

        with Session(engine) as session:
            for address in contract_addresses:
                latest_block = get_latest_block(session, address, chain)
                page = 1
                while True:
                    transactions = get_transactions(
                        address, latest_block + 1, MAX_BLOCK_NUMBER, page, offset=100
                    )
                    if not transactions:
                        break

                    for tx in transactions:
                        if tx["isError"] == "1":
                            continue

                        tx_data = process_transaction(tx, chain)
                        new_transaction = OnchainTransactionHistory(**tx_data)
                        session.add(new_transaction)
                    session.commit()
                    page += 1
        
        logger.info("Stop indexing transaction %s %s", contract_addresses, chain)
    except Exception as e:
        logger.error(f"Error occurred: {e}")
        logger.error(traceback.format_exc())
        raise e


@click.group()
def cli():
    pass


@cli.command()
@click.option(
    "--chain", required=True, help="Blockchain network chain", type=NetworkChain
)
def historical(chain: NetworkChain):
    if chain == NetworkChain.arbitrum_one:
        contract_addresses = [
            Web3.to_checksum_address("0x2b7cdad36a86fd05ac1680cdc42a0ea16804d80c"),
            Web3.to_checksum_address("0xF30353335003E71b42a89314AAaeC437E7Bc8F0B"),
            Web3.to_checksum_address("0x4a10C31b642866d3A3Df2268cEcD2c5B14600523"),
            Web3.to_checksum_address("0x316CDbBEd9342A1109D967543F81FA6288eBC47D"),
            Web3.to_checksum_address("0xd531d9212cB1f9d27F9239345186A6e9712D8876"),
        ]
    elif chain == NetworkChain.ethereum:
        contract_addresses = [
            Web3.to_checksum_address("0x09f2b45a6677858f016EBEF1E8F141D6944429DF"),
            Web3.to_checksum_address("0xFae8821DD6e5F93431506bf234Ed94dDaaD2A533"),
            
        ]

    index_transactions(contract_addresses, chain)


@cli.command()
@click.option("--address", required=True, help="Vault address", type=str)
@click.option(
    "--chain", required=True, help="Blockchain network chain", type=NetworkChain
)
def live(address, chain: NetworkChain):
    setup_logging_to_console()
    setup_logging_to_file(
        f"indexing_historical_transactions_data_{chain.value}_{address}", logger=logger
    )
    index_transactions([address], chain)
    sys.exit(0)


if __name__ == "__main__":
    cli()
