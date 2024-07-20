import logging
from web3 import AsyncWeb3
import config
from utils import abi_reader
from utils.web3_utils import parse_hex_to_int, sign_and_send_transaction

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
    def __init__(self, web3: AsyncWeb3, network_chain_id):
        self.web3 = web3
        self.abi = abi_reader.read_abi("UniSwap")
        self.network_chain_id = network_chain_id
        self.contract_address = config.UNISWAP_PROXY_ADDRESS[self.network_chain_id]
        self.contract = self.web3.eth.contract(
            address=self.contract_address, abi=self.abi
        )

    async def _get_direct_from_pool(self, token1: str, token2: str) -> int:
        if self.network_chain_id == config.CHAIN_ARBITRUM:
            pool_address = config.ARB_UNISWAP_WETH_USDC_POOL_ADDRESS
        elif self.network_chain_id == config.CHAIN_BASE:
            pool_address = config.BASE_UNISWAP_WETH_USDC_POOL_ADDRESS
        elif self.network_chain_id == config.CHAIN_ETHER_MAINNET:
            pool_address = config.ETHER_UNISWAP_WETH_USDC_POOL_ADDRESS
        else:
            raise Exception("Not implemented")

        pool_contract = self.web3.eth.contract(
            address=pool_address, abi=POOL_ADDRESS_ABI
        )
        price = await pool_contract.functions.slot0().call()
        sqrt_price_x96 = price[0]
        price = (sqrt_price_x96**2) / (2**192)

        if self.network_chain_id == config.CHAIN_ETHER_MAINNET:
            # due to uniswap only have pool USDC/ETH so we need to reverse the price
            return int(1 / price * 1e12 * 1e6)

        return int(price * 1e12 * 1e6)

    async def get_price_of(self, token1: str, token2: str):
        if (
            token1 == config.WETH_CONTRACT_ADDRESS[self.network_chain_id]
            and token2 == config.USDC_ADDRESS[self.network_chain_id]
        ):
            return await self._get_direct_from_pool(token1, token2)

        price = await self.contract.functions.getPriceOf(token1, token2).call()
        return price