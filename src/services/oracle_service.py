from web3 import Web3

from core import constants

oracle_abi = [
    {
        "inputs": [],
        "name": "latestAnswer",
        "outputs": [{"internalType": "int256", "name": "", "type": "int256"}],
        "stateMutability": "view",
        "type": "function",
    }
]


def get_oracle_price(web3: Web3, decimals: int, block_number: int = None):
    feed_address = constants.FEED_ADDRESS
    contract = web3.eth.contract(address=feed_address, abi=oracle_abi)
    latest_answer = contract.functions.latestAnswer().call(
        block_identifier=block_number
    )
    price = latest_answer / (10**decimals)
    return price
