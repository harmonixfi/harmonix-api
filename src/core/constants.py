from enum import Enum
from core.config import settings

RENZO = "renzo"
ZIRCUIT = "zircuit"
KELPDAO = "kelpdao"
EIGENLAYER = "eigenlayer"
HARMONIX = "Harmonix"
BSX = "bsx"

REWARD_HIGH_PERCENTAGE = 0.08
REWARD_DEFAULT_PERCENTAGE = 0.05
REWARD_HIGH_LIMIT = 101
MIN_FUNDS_FOR_HIGH_REWARD = 50.0
HIGH_REWARD_DURATION_DAYS = 90

REFERRAL_POINTS_PERCENTAGE = 0.1

OPTIONS_WHEEL_STRATEGY = "options_wheel_strategy"
DELTA_NEUTRAL_STRATEGY = "delta_neutral_strategy"

NETWORK_RPC_URLS = {
    "arbitrum_one": settings.ARBITRUM_MAINNET_INFURA_URL,
    "ethereum": settings.ETHER_MAINNET_INFURA_URL,
    "base": settings.BASE_MAINNET_NETWORK_RPC,
}

NETWORK_SOCKET_URLS = {
    "arbitrum_one": settings.ARBITRUM_MAINNET_INFURA_WEBSOCKER_URL,
    "ethereum": settings.ETHER_MAINNET_INFURA_URL,
    "base": settings.BASE_MAINNET_WSS_NETWORK_RPC,
}

class Status(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"
