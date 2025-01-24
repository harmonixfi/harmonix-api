from enum import Enum

from web3 import Web3
from core.config import settings

RENZO = "renzo"
ZIRCUIT = "zircuit"
KELPDAO = "kelpdao"
EIGENLAYER = "eigenlayer"
HARMONIX = "Harmonix"
HARMONIX_MKT = "Harmonix-mkt"
HYPERLIQUID = "Hyperliquid"
BSX = "bsx"
GOLDLINK = "goldlink"

PARTNER_GODLINK = "goldlink"

PARTNER_KELPDAOGAIN = "kelpdaogain"
EARNED_POINT_LINEA = "linea"
EARNED_POINT_SCROLL = "scroll"
EARNED_POINT_KARAK = "karak"
EARNED_POINT_INFRA_PARTNER = "infra partner"

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
GOLD_LINK_SLUG = "arbitrum-leverage-delta-neutral-link"
ETH_WITH_LENDING_BOOST_YIELD = "arbitrum-delta-neutral-boost-yield-eth"
PENDLE_RSETH_26DEC24_SLUG = "arbitrum-pendle-rseth-26dec2024"
PENDLE_RSETH_26JUN25_SLUG = "arbitrum-pendle-rseth-26jun2025"
HYPE_DELTA_NEUTRAL_SLUG = "hype-delta-neutral-v1"

CHAIN_ARBITRUM = "arbitrum_one"
CHAIN_ETHER_MAINNET = "ethereum"
CHAIN_BASE = "base"

CHAIN_IDS = {"CHAIN_ARBITRUM": 42161}

FEED_ADDRESS = Web3.to_checksum_address("0x639Fe6ab55C921f74e7fac1ee960C0B6293ba612")

CAMELOT_LP_POOL = {
    "WST_ETH_ADDRESS": "0xdEb89DE4bb6ecf5BFeD581EB049308b52d9b2Da7",
    "USDE_USDC_ADDRESS": "0xc23f308CF1bFA7efFFB592920a619F00990F8D74",
}


SOLV_VAULT_SLUG = "arbitrum-wbtc-vault"
BSX_VAULT_SLUG = "base-wsteth-delta-neutral"
KELPDAO_VAULT_ARBITRUM_SLUG = "kelpdao-restaking-delta-neutral-vault"
RENZO_VAULT_SLUG = "renzo-zircuit-restaking-delta-neutral-vault"
DELTA_NEUTRAL_VAULT_VAULT_SLUG = "delta-neutral-vault"
OPTIONS_WHEEL_VAULT_VAULT_SLUG = "options-wheel-vault"
PENDLE_VAULT_VAULT_SLUG = "arbitrum-pendle-rseth-26sep2024"
KELPDAO_GAIN_VAULT_SLUG = "ethereum-kelpdao-gain-restaking-delta-neutral-vault"
PENDLE_VAULT_VAULT_SLUG_DEC = "arbitrum-pendle-rseth-26dec2024"
KELPDAO_VAULT_SLUG = "ethereum-kelpdao-restaking-delta-neutral-vault"

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

AGETH_ADDRESS: dict = {
    CHAIN_ETHER_MAINNET: "0xe1B4d34E8754600962Cd944B535180Bd758E6c2e",
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

MAX_SLIPPAGE = 'max_slippage'
TRADING_FEE = 'trading_fee'
SPOT_PERP_SPREAD = 'spot_perp_spread'
PERFORMANCE_FEE = 'performance_fee'
MANAGEMENT_FEE = 'management_fee'

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
    DEPOSIT4 = "0xfaa9bce9"
    DEPOSIT5 = "0x49bdc2b8"
    DEPOSIT_RETHINK1 = "0xdb6b5246"
    DEPOSIT_RETHINK2 = "0x690e0dda"
    WITHDRAW = "0x12edde5e"
    WITHDRAW_PENDLE1 = "0x087fad4c"
    WITHDRAW_PENDLE2 = "0xb51d1d4f"
    COMPPLETE_WITHDRAWAL = "0x4f0cb5f3"
    COMPPLETE_WITHDRAWAL2 = "0xe03ff7cb"


class UpdateFrequency(str, Enum):
    daily = "daily"
    weekly = "weekly"


class AppConfigKey(str, Enum):
    APY_PERIOD = "apy_period"
