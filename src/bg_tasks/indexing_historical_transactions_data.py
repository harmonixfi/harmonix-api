import time
import logging
import sys
import traceback
import click
from web3 import Web3
from sqlmodel import Session, select
from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models.onchain_transaction_history import OnchainTransactionHistory
from models.vaults import NetworkChain, Vault
from services import arbiscan_service, basescan_service, etherscan_service

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
        elif chain == NetworkChain.base:
            get_transactions = basescan_service.get_transactions
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
                    logger.info("Get list transactions %s", transactions)
                    
                    if not transactions:
                        time.sleep(0.5)
                        break

                    for tx in transactions:
                        if tx["isError"] == "1":
                            continue

                        tx_data = process_transaction(tx, chain)
                        new_transaction = OnchainTransactionHistory(**tx_data)
                        session.add(new_transaction)
                    session.commit()
                    page += 1
                    time.sleep(0.5)

        logger.info("Stop indexing transaction %s %s", contract_addresses, chain)
    except Exception as e:
        logger.error(f"Error occurred: {e}")
        logger.error(traceback.format_exc())
        raise e


def live_index_data():
    with Session(engine) as session:
        for network_chain in [
            NetworkChain.arbitrum_one,
            NetworkChain.ethereum,
            NetworkChain.base,
        ]:
            vaults = session.exec(
                select(Vault)
                .where(Vault.is_active == True)
                .where(Vault.network_chain == network_chain)
            ).all()

            addresses = [v.contract_address for v in vaults]
            index_transactions(addresses, network_chain)


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
            # kelp dao
            Web3.to_checksum_address("0x2b7cdad36a86fd05ac1680cdc42a0ea16804d80c"),
            Web3.to_checksum_address("0xF30353335003E71b42a89314AAaeC437E7Bc8F0B"),
            Web3.to_checksum_address("0x4a10C31b642866d3A3Df2268cEcD2c5B14600523"),
            # delta-neutral-vault
            Web3.to_checksum_address("0x50cddcba6289d3334f7d40cf5d312e544576f0f9"),
            Web3.to_checksum_address("0xc9a079d7d1cf510a6dba8da8494745beae7736e2"),
            Web3.to_checksum_address("0x389b5702fa8bf92759d676036d1a90516c1ce0c4"),
            Web3.to_checksum_address("0xd531d9212cb1f9d27f9239345186a6e9712d8876"),
            Web3.to_checksum_address("0x607b19a600f2928fb4049d2c593794fb70aaf9aa"),
            # The Golden Guardian with Solv
            Web3.to_checksum_address("0x9d95527A298c68526Ad5227fe241B75329D3b91F"),
            # Koi Doing Dragon's Dance
            Web3.to_checksum_address("0x316CDbBEd9342A1109D967543F81FA6288eBC47D"),
            Web3.to_checksum_address("0x0bD37D11e3A25B5BB0df366878b5D3f018c1B24c"),
            Web3.to_checksum_address("0x18994527E6FfE7e91F1873eCA53e900CE0D0f276"),
            Web3.to_checksum_address("0x55c4c840F9Ac2e62eFa3f12BaBa1B57A1208B6F5"),
        ]
    elif chain == NetworkChain.ethereum:
        contract_addresses = [
            # kelp dao
            Web3.to_checksum_address("0x09f2b45a6677858f016EBEF1E8F141D6944429DF"),
            # Fin-tastic with Renzo
            Web3.to_checksum_address("0xFae8821DD6e5F93431506bf234Ed94dDaaD2A533"),
        ]
    elif chain == NetworkChain.base:
        contract_addresses = [
            # Shimmer & Fin with BSX
            Web3.to_checksum_address("0x99CD3fd86303eEfb71D030e6eBfA12F4870bD01F"),
        ]
    index_transactions(contract_addresses, chain)


@cli.command()
def live():
    setup_logging_to_console()
    # setup_logging_to_file(
    #     f"indexing_historical_transactions_data_{chain.value}_{address}", logger=logger
    # )
    live_index_data()
    sys.exit(0)


if __name__ == "__main__":
    cli()
