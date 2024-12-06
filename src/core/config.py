import secrets
from typing import Any, List, Optional, Union
from pydantic import AnyHttpUrl, Extra, validator
from pydantic_settings import BaseSettings

from pydantic import (
    AnyHttpUrl,
    HttpUrl,
    PostgresDsn,
    ValidationInfo,
    field_validator,
)
from web3 import Web3


class Settings(BaseSettings):

    ENVIRONMENT_NAME: str

    @property
    def is_production(self):
        return self.ENVIRONMENT_NAME == "Production"

    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = secrets.token_urlsafe(32)
    # 60 minutes * 24 hours * 8 days = 8 days
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 30
    SERVER_NAME: str
    SERVER_HOST: AnyHttpUrl
    # BACKEND_CORS_ORIGINS is a JSON-formatted list of origins
    # e.g: '["http://localhost", "http://localhost:4200", "http://localhost:3000", \
    # "http://localhost:8080", "http://local.dockertoolbox.tiangolo.com"]'
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []

    @validator("BACKEND_CORS_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    PROJECT_NAME: str

    ETHER_MAINNET_INFURA_URL: str | None = None
    ETHER_MAINNET_INFURA_WEBSOCKER_URL: str | None = None

    BASE_MAINNET_NETWORK_RPC: str
    BASE_MAINNET_WSS_NETWORK_RPC: str

    ARBITRUM_MAINNET_INFURA_URL: str
    ARBITRUM_MAINNET_INFURA_WEBSOCKER_URL: str

    SEPOLIA_TESTNET_INFURA_WEBSOCKER_URL: str
    SEPOLIA_TESTNET_INFURA_URL: str

    WSTETH_ADDRESS: str = "0x5979D7b546E38E414F7E9822514be443A4800529"
    USDC_ADDRESS: str = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
    USDCE_ADDRESS: str = "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8"
    DAI_ADDRESS: dict = {
        "arbitrum_one": "0xda10009cbd5d07dd0cecc66161fc93d7c9000da1",
        "ethereum": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
    }
    ROCKONYX_STABLECOIN_ADDRESS: str = ""
    ROCKONYX_DELTA_NEUTRAL_VAULT_ADDRESS: str = ""
    ROCKONYX_RENZO_ZIRCUIT_RESTAKING_DELTA_NEUTRAL_VAULT_ADDRESS: str = ""
    ROCKONYX_RENZO_ARB_RESTAKING_DELTA_NEUTRAL_VAULT_ADDRESS: str = ""
    ROCKONYX_KELPDAO_ARB_RESTAKING_DELTA_NEUTRAL_VAULT_ADDRESS: str = ""
    ROCKONYX_USDCE_USDC_PRICE_FEED_ADDRESS: str
    USDCE_USDC_CAMELOT_POOL_ADDRESS: str

    STABLECOIN_DEPOSIT_VAULT_FILTER_TOPICS: str = Web3.solidity_keccak(
        ["string"], ["Deposited(address,uint256,uint256)"]
    ).hex()
    STABLECOIN_INITIATE_WITHDRAW_VAULT_FILTER_TOPICS: str = Web3.solidity_keccak(
        ["string"], ["InitiateWithdrawal(address,uint256,uint256)"]
    ).hex()
    STABLECOIN_COMPLETE_WITHDRAW_VAULT_FILTER_TOPICS: str = Web3.solidity_keccak(
        ["string"], ["Withdrawn(address,uint256,uint256)"]
    ).hex()

    MULTIPLE_STABLECOINS_DEPOSIT_EVENT_TOPIC: str = Web3.solidity_keccak(
        ["string"], ["Deposited(address,address,uint256,uint256)"]
    ).hex()
    DELTA_NEUTRAL_DEPOSIT_EVENT_TOPIC: str = Web3.solidity_keccak(
        ["string"], ["Deposited(address,uint256,uint256)"]
    ).hex()
    DELTA_NEUTRAL_INITIATE_WITHDRAW_EVENT_TOPIC: str = Web3.solidity_keccak(
        ["string"], ["RequestFunds(address,uint256,uint256)"]
    ).hex()
    DELTA_NEUTRAL_COMPLETE_WITHDRAW_EVENT_TOPIC: str = Web3.solidity_keccak(
        ["string"], ["Withdrawn(address,uint256,uint256)"]
    ).hex()

    SOLV_DEPOSIT_EVENT_TOPIC: str = Web3.solidity_keccak(
        ["string"], ["Deposit(address,address,uint256,uint256)"]
    ).hex()
    SOLV_INITIATE_WITHDRAW_EVENT_TOPIC: str = Web3.solidity_keccak(
        ["string"], ["RequestFunds(address,address,uint256)"]
    ).hex()
    SOLV_COMPLETE_WITHDRAW_EVENT_TOPIC: str = Web3.solidity_keccak(
        ["string"], ["Withdrawn(address,address,uint256,uint256)"]
    ).hex()

    # PENDLE TOPICS
    PENDLE_DEPOSIT_EVENT_TOPIC: str = Web3.solidity_keccak(
        ["string"], ["Deposit(address,uint256,uint256,uint256,uint256,uint256)"]
    ).hex()

    PENDLE_REQUEST_FUND_EVENT_TOPIC: str = Web3.solidity_keccak(
        ["string"], ["RequestFunds(address,uint256,uint256,uint256,uint256,uint256)"]
    ).hex()

    PENDLE_FORCE_REQUEST_FUND_EVENT_TOPIC: str = Web3.solidity_keccak(
        ["string"],
        ["ForceRequestFunds(address,uint256,uint256,uint256,uint256,uint256)"],
    ).hex()

    PENDLE_COMPLETE_WITHDRAW_EVENT_TOPIC: str = Web3.solidity_keccak(
        ["string"], ["Withdrawn(address,uint256,uint256,uint256,uint256)"]
    ).hex()

    RETHINK_DELTA_NEUTRAL_DEPOSIT_EVENT_TOPIC: str = Web3.solidity_keccak(
        ["string"], ["UserDeposited(address,uint256)"]
    ).hex()

    RETHINK_DELTA_NEUTRAL_DEPOSITED_TO_FUND_CONTRACT_EVENT_TOPIC: str = Web3.solidity_keccak(
        ["string"], ["DepositedToFundContract(uint256)"]
    ).hex()
    RETHINK_DELTA_NEUTRAL_REQUEST_FUND_EVENT_TOPIC: str = Web3.solidity_keccak(
        ["string"], ["InitiateWithdrawal(address,uint256,uint256)"]
    ).hex()
    RETHINK_DELTA_NEUTRAL_COMPLETE_WITHDRAW_EVENT_TOPIC: str = Web3.solidity_keccak(
        ["string"], ["Withdrawn(address,uint256,uint256)"]
    ).hex()

    OPTIONS_WHEEL_OWNER_WALLET_ADDRESS: str

    OPERATION_ADMIN_WALLET_ADDRESS: str
    OPERATION_ADMIN_WALLET_PRIVATE_KEY: str

    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    SQLALCHEMY_DATABASE_URI: PostgresDsn | None = None

    PYTHONPATH: Optional[str] = None
    NODE_ENV: Optional[str] = None
    NEXT_PUBLIC_THIRD_WEB_CLIENT_ID: Optional[str] = None
    NEXT_PUBLIC_API_URL: Optional[str] = None
    NEXT_PUBLIC_ROCK_ONYX_USDT_VAULT_ADDRESS: Optional[str] = None
    NEXT_PUBLIC_USDC_ADDRESS: Optional[str] = None

    # RESTAKING
    RENZO_BASE_API_URL: Optional[str] = "https://app.renzoprotocol.com/api/"
    ZIRCUIT_BASE_API_URL: Optional[str] = "https://stake.zircuit.com/api/"
    KELPDAO_BASE_API_URL: Optional[str] = "https://common.kelpdao.xyz/"
    KYBERSWAP_BASE_API_URL: Optional[str] = "https://aggregator-api.kyberswap.com"
    KELPGAIN_BASE_API_URL: Optional[str] = "https://common.kelpdao.xyz/"

    SNS_SYSTEM_MONITORING_URL: Optional[str] = (
        "https://sqs.ap-southeast-1.amazonaws.com/471112945627/system-monitoring-queue"
    )
    SNS_SYSTEM_API_KEY: Optional[str] = ""
    SNS_SYSTEM_API_SECRET: Optional[str] = ""

    # Seq log
    SEQ_SERVER_URL: Optional[str] = None
    SEQ_SERVER_API_KEY: Optional[str] = None

    ARBISCAN_API_KEY: str
    ARBISCAN_GET_TRANSACTIONS_URL: str = (
        "https://api.arbiscan.io/api?module=account&action=txlist"
    )

    ETHERSCAN_API_KEY: str
    ETHERSCAN_GET_TRANSACTIONS_URL: str = (
        "https://api.etherscan.io/api?module=account&action=txlist"
    )

    HYPERLIQUID_URL: Optional[str] = "https://api.hyperliquid.xyz/info"

    BASESCAN_API_KEY: str
    BASESCAN_GET_TRANSACTIONS_URL: str = (
        "https://api.basescan.org/api?module=account&action=txlist"
    )
    SOLV_API_KEY: str

    BSX_API_KEY: Optional[str] = None
    BSX_SECRET: Optional[str] = None
    BSX_BASE_API_URL: Optional[str] = None

    TRANSACTION_ALERTS_GROUP_CHATID: Optional[str] = None
    SYSTEM_ERROR_ALERTS_GROUP_CHATID: Optional[str] = None
    TELEGRAM_TOKEN: Optional[str] = None

    PENDLE_API_URL: Optional[str] = "https://api-v2.pendle.finance/core/v1"
    KELPDAO_API_URL: Optional[str] = "https://universe.kelpdao.xyz"
    RENZO_API_URL: Optional[str] = "https://app.renzoprotocol.com/api/stats?chainId=1"
    LIDO_API_URL: Optional[str] = "https://eth-api.lido.fi"
    CAMELOT_EXCHANGE_API_URL: Optional[str] = "https://api.camelot.exchange"

    AEVO_API_URL: Optional[str] = "https://api.aevo.xyz"
    GOLD_LINK_API_URL: Optional[str] = "https://api.goldlink.io"
    GOLD_LINK_NETWORK_ID_MAINNET: Optional[str] = (
        "0xB4E29A1A0E6F9DB584447E988CE15D48A1381311"
    )
    GOLD_LINK_ETH_NETWORK_ID_MAINNET: Optional[str] = (
        "0x7f1fa204bb700853d36994da19f830b6ad18455c"
    )
    GOLDLINK_REWARD_CONTRACT_ADDRESS: str = "0xa9BE190b8348F18466dC84cC2DE69C04673c5aca"

    BASIC_AUTH_USERNAME: str
    BASIC_AUTH_PASSWORD: str

    WHITELIST_WALLETS_RETHINK: str = "0x658e36f00B397EC7aAEF9f465FB05E1aeC9a8363,0x04A4b0489E9198f0A0eC3BC938EaBf13498C6F8d,0x216F547F01e01FF0f3c69375d6a0B80d9d6DEdFA"

    @field_validator("SQLALCHEMY_DATABASE_URI", mode="before")
    def assemble_db_connection(cls, v: str | None, info: ValidationInfo) -> Any:
        if isinstance(v, str):
            return v
        return PostgresDsn.build(
            scheme="postgresql+psycopg",
            username=info.data.get("POSTGRES_USER"),
            password=info.data.get("POSTGRES_PASSWORD"),
            host=info.data.get("POSTGRES_SERVER"),
            path=f"{info.data.get('POSTGRES_DB') or ''}",
        )

    class Config:

        case_sensitive = True
        env_file = "../.env"
        extra = "allow"


settings = Settings()
