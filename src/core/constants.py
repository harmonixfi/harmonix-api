from enum import Enum

from web3 import Web3
from core.config import settings

RENZO = "renzo"
ZIRCUIT = "zircuit"
KELPDAO = "kelpdao"
EIGENLAYER = "eigenlayer"
HARMONIX = "Harmonix"
HYPERLIQUID = "Hyperliquid"
BSX = "bsx"

REWARD_HIGH_PERCENTAGE = 0.08
REWARD_DEFAULT_PERCENTAGE = 0.05
REWARD_KOL_AND_PARTNER_DEFAULT_PERCENTAGE = 0.06
REWARD_HIGH_LIMIT = 101
MIN_FUNDS_FOR_HIGH_REWARD = 50.0
HIGH_REWARD_DURATION_DAYS = 90

REFERRAL_POINTS_PERCENTAGE = 0.1

OPTIONS_WHEEL_STRATEGY = "options_wheel_strategy"
DELTA_NEUTRAL_STRATEGY = "delta_neutral_strategy"
PENDLE_HEDGING_STRATEGY = "pendle_hedging_strategy"
STAKING_STRATEGY = "staking_strategy"

SOLV_VAULT_SLUG = "arbitrum-wbtc-vault"
BSX_VAULT_SLUG = "base-wsteth-delta-neutral"

CHAIN_ARBITRUM = "arbitrum_one"
CHAIN_ETHER_MAINNET = "ethereum"
CHAIN_BASE = "base"

CHAIN_IDS = {"CHAIN_ARBITRUM": 42161}

FEED_ADDRESS = Web3.to_checksum_address("0x639Fe6ab55C921f74e7fac1ee960C0B6293ba612")

NETWORK_RPC_URLS = {
    CHAIN_ARBITRUM: settings.ARBITRUM_MAINNET_INFURA_URL,
    CHAIN_ETHER_MAINNET: settings.ETHER_MAINNET_INFURA_URL,
    CHAIN_BASE: settings.BASE_MAINNET_NETWORK_RPC,
}

NETWORK_SOCKET_URLS = {
    CHAIN_ARBITRUM: settings.ARBITRUM_MAINNET_INFURA_WEBSOCKER_URL,
    CHAIN_ETHER_MAINNET: settings.ETHER_MAINNET_INFURA_URL,
    CHAIN_BASE: settings.BASE_MAINNET_WSS_NETWORK_RPC,
}

WSTETH_ADDRESS: dict = {
    CHAIN_ARBITRUM: "0x5979D7b546E38E414F7E9822514be443A4800529",
    CHAIN_ETHER_MAINNET: "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0",
}

WETH_ADDRESS: dict = {
    CHAIN_ARBITRUM: "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
    CHAIN_ETHER_MAINNET: "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0",
}

RSETH_ADDRESS: dict = {
    CHAIN_ARBITRUM: "0x4186BFC76E2E237523CBC30FD220FE055156b41F",
    CHAIN_ETHER_MAINNET: "0xA1290d69c65A6Fe4DF752f95823fae25cB99e5A7",
}

USDC_ADDRESS: dict = {
    CHAIN_ARBITRUM: "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    CHAIN_ETHER_MAINNET: "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
}
USDCE_ADDRESS: dict = {
    CHAIN_ARBITRUM: "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8",
}

DAI_ADDRESS: dict = {
    CHAIN_ARBITRUM: "0xda10009cbd5d07dd0cecc66161fc93d7c9000da1",
    CHAIN_ETHER_MAINNET: "0x6B175474E89094C44Da98b954EedeAC495271d0F",
}

RSETH_ADDRESS: dict = {
    CHAIN_ARBITRUM: "0x4186BFC76E2E237523CBC30FD220FE055156b41F",
    CHAIN_ETHER_MAINNET: "0xA1290d69c65A6Fe4DF752f95823fae25cB99e5A7",
}

ZIRCUIT_DEPOSIT_CONTRACT_ADDRESS = "0xF047ab4c75cebf0eB9ed34Ae2c186f3611aEAfa6"

ZIRCUIT_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "", "type": "address"},
            {"internalType": "address", "name": "", "type": "address"},
        ],
        "name": "balance",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
]


ARB_UNISWAP_WETH_USDC_POOL_ADDRESS = "0xC6962004f452bE9203591991D15f6b388e09E8D0"
ETH_UNISWAP_WETH_USDC_POOL_ADDRESS = "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640"

UNISWAP_POOLS = {
    WETH_ADDRESS[CHAIN_ARBITRUM]: {
        USDC_ADDRESS[CHAIN_ARBITRUM]: ARB_UNISWAP_WETH_USDC_POOL_ADDRESS
    },
    WETH_ADDRESS[CHAIN_ETHER_MAINNET]: {
        USDC_ADDRESS[CHAIN_ETHER_MAINNET]: ETH_UNISWAP_WETH_USDC_POOL_ADDRESS
    },
}

DAI_CONTRACT_ADDRESS = "0xda10009cbd5d07dd0cecc66161fc93d7c9000da1"
VAULT_SOLV_NAME = "The Golden Guardian with Solv"


class Status(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"


class UserTier(str, Enum):
    DEFAULT = "default"
    KOL = "kol"
    PARTNER = "partner"


monthly_new_tvl_threshold = {
    "zero": 0,
    "500k": 500000,
    "1M": 1000000,
    "1.5m": 1500000,
}


class Campaign(str, Enum):
    DEFAULT = "default"
    REFERRAL_101 = "referral_101"
    KOL_AND_PARTNER = "kol_and_partner"


class MethodID(str, Enum):
    DEPOSIT = "0x2e2d2984"
    DEPOSIT2 = "0xb6b55f25"
    DEPOSIT3 = "0x71b8dc69"
    WITHDRAW = "0x12edde5e"
    COMPPLETE_WITHDRAWAL = "0x4f0cb5f3"
    COMPPLETE_WITHDRAWAL2 = "0xe03ff7cb"


class UpdateFrequency(str, Enum):
    daily = "daily"
    weekly = "weekly"
