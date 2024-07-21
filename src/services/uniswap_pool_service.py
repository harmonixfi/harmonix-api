import logging
from web3 import AsyncWeb3, Web3
from core import constants

logger = logging.getLogger("delta_neutral")


POOL_ADDRESS_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"name": "sqrtPriceX96", "type": "uint160"},
            {"name": "tick", "type": "int24"},
            {"name": "observationIndex", "type": "uint16"},
            {"name": "observationCardinality", "type": "uint16"},
            {"name": "observationCardinalityNext", "type": "uint16"},
            {"name": "feeProtocol", "type": "uint8"},
            {"name": "unlocked", "type": "bool"},
        ],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    }
]


class Uniswap:
    def __init__(self, web3: Web3, network_chain_id):
        self.web3 = web3
        self.network_chain_id = network_chain_id

    def _get_direct_from_pool(self, token1: str, token2: str, block_number: int) -> int:
        try:
            pool_address = constants.UNISWAP_POOLS[token1][token2]
        except KeyError:
            raise Exception(f"Pool address not found for {token1}/{token2}")

        pool_contract = self.web3.eth.contract(
            address=pool_address, abi=POOL_ADDRESS_ABI
        )
        price = pool_contract.functions.slot0().call(block_identifier=block_number)
        sqrt_price_x96 = price[0]
        price = (sqrt_price_x96**2) / (2**192)

        if self.network_chain_id == constants.CHAIN_ETHER_MAINNET:
            # due to uniswap only have pool USDC/ETH so we need to reverse the price
            return int(1 / price * 1e12 * 1e6)

        return int(price * 1e12 * 1e6)

    def get_price_of(
        self, token1: str, token2: str, block_number: int = None
    ) -> int:
        if block_number is None:
            block_number = self.web3.eth.block_number

        price = self._get_direct_from_pool(token1, token2, block_number)
        return price
