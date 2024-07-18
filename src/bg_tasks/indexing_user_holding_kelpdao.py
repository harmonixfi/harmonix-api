from sqlmodel import Session, select
from web3 import Web3
from core.abi_reader import read_abi
from core.config import settings
from core.db import engine
from models.onchain_transaction_history import OnchainTransactionHistory


w3 = Web3(Web3.HTTPProvider(settings.ARBITRUM_MAINNET_INFURA_URL))

rockonyx_delta_neutral_vault_abi = read_abi("rockonyxrestakingdeltaneutralvault")
vault_contract = w3.eth.contract(
    address="0x4a10C31b642866d3A3Df2268cEcD2c5B14600523",
    abi=rockonyx_delta_neutral_vault_abi,
)


def get_user_balance(address: str, block_number: int) -> float:
    balance = vault_contract.functions.balanceOf(Web3.to_checksum_address(address)).call(block_identifier=block_number)
    return balance / 1e6


def calculate_rseth_holding():
    with Session(engine) as session:
        # fetch all OnchainTransactionHistory order by block_number asc
        transactions = session.exec(
            select(OnchainTransactionHistory).order_by(
                OnchainTransactionHistory.block_number.asc()
            )
        )

        for tx in transactions:
            if tx.method_id == '0x2e2d2984':  # Deposit

