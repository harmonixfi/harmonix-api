import logging
from typing import List, Tuple
from sqlalchemy import func
from sqlmodel import Session, select
from datetime import datetime, timedelta
import uuid
import pytz
from telegram import Contact
from web3 import Web3

from core import constants
from models.vaults import Vault
from utils.extension_utils import (
    to_amount_pendle,
    to_tx_aumount,
)
from utils.web3_utils import get_current_pps_by_block
from core.abi_reader import read_abi


class VaultContractService:
    def __init__(self):
        pass

    def get_vault_contract(
        self,
        network_chain: str,
        contract_address,
        abi_name: str = "RockOnyxDeltaNeutralVault",
    ) -> tuple[Contact, Web3]:

        w3 = Web3(Web3.HTTPProvider(constants.NETWORK_RPC_URLS[network_chain]))

        rockonyx_delta_neutral_vault_abi = read_abi(abi_name)
        vault_contract = w3.eth.contract(
            address=contract_address,
            abi=rockonyx_delta_neutral_vault_abi,
        )
        return vault_contract, w3

    def get_vault_abi(self, vault: Vault):
        abi = "RockOnyxDeltaNeutralVault"

        if vault.slug == constants.SOLV_VAULT_SLUG:
            abi = "solv"
        elif vault.strategy_name == constants.DELTA_NEUTRAL_STRATEGY:
            abi = "RockOnyxDeltaNeutralVault"
        elif vault.strategy_name == constants.OPTIONS_WHEEL_STRATEGY:
            abi = "rockonyxstablecoin"
        elif vault.strategy_name == constants.PENDLE_HEDGING_STRATEGY:
            abi = "pendlehedging"

        return abi

    def get_withdraw_amount(
        self, vault: Vault, to_address: str, input_data: str, block_number: int
    ) -> float:
        if vault.strategy_name == constants.PENDLE_HEDGING_STRATEGY:
            return to_amount_pendle(input_data, block_number, vault.network_chain)

        abi = self.get_vault_abi(vault=vault)
        shares = to_tx_aumount(input_data)
        vault_contract, _ = self.get_vault_contract(
            vault.network_chain,
            Web3.to_checksum_address(to_address),
            abi,
        )
        pps = get_current_pps_by_block(vault_contract, block_number)
        return shares * pps

    def get_vault_address_historical(self, vault: Vault) -> List[str]:
        if (
            vault.contract_address.lower()
            == "0x4a10c31b642866d3a3df2268cecd2c5b14600523".lower()
        ):
            return [
                "0x4a10c31b642866d3a3df2268cecd2c5b14600523",
                "0xF30353335003E71b42a89314AAaeC437E7Bc8F0B",
                "0x2b7cdad36a86fd05ac1680cdc42a0ea16804d80c",
            ]

        if (
            vault.contract_address.lower()
            == "0xd531d9212cB1f9d27F9239345186A6e9712D8876".lower()
        ):
            return [
                "0x50CDDCBa6289d3334f7D40cF5d312E544576F0f9",
                "0x607b19a600F2928FB4049d2c593794fB70aaf9aa",
                "0xC9A079d7d1CF510a6dBa8dA8494745beaE7736E2",
                "0x389b5702FA8bF92759d676036d1a90516C1ce0C4",
                "0xd531d9212cB1f9d27F9239345186A6e9712D8876",
            ]
        if (
            vault.contract_address.lower()
            == "0x316CDbBEd9342A1109D967543F81FA6288eBC47D".lower()
        ):
            return [
                vault.contract_address,
                "0x0bD37D11e3A25B5BB0df366878b5D3f018c1B24c",
                "0x18994527E6FfE7e91F1873eCA53e900CE0D0f276",
                "0x55c4c840F9Ac2e62eFa3f12BaBa1B57A1208B6F5",
            ]

        return [vault.contract_address.lower()]

    def get_vault_address_by_contract(self, contract_address: str) -> List[str]:
        contract_address = contract_address.lower()
        vault_addresses = {
            "0x4a10c31b642866d3a3df2268cecd2c5b14600523": [
                "0x4a10c31b642866d3a3df2268cecd2c5b14600523",
                "0xF30353335003E71b42a89314AAaeC437E7Bc8F0B",
                "0x2b7cdad36a86fd05ac1680cdc42a0ea16804d80c",
            ],
            "0xd531d9212cb1f9d27f9239345186a6e9712d8876": [
                "0x50CDDCBa6289d3334f7D40cF5d312E544576F0f9",
                "0x607b19a600F2928FB4049d2c593794fB70aaf9aa",
                "0xC9A079d7d1CF510a6dBa8dA8494745beaE7736E2",
                "0x389b5702FA8bF92759d676036d1a90516C1ce0C4",
                "0xd531d9212cb1f9d27f9239345186a6e9712d8876",
            ],
            "0x316cdbbed9342a1109d967543f81fa6288ebc47d": [
                "0x316cdbbed9342a1109d967543f81fa6288ebc47d",
                "0x0bD37D11e3A25B5BB0df366878b5D3f018c1B24c",
                "0x18994527E6FfE7e91F1873eCA53e900CE0D0f276",
                "0x55c4c840F9Ac2e62eFa3f12BaBa1B57A1208B6F5",
            ],
        }

        for addresses in vault_addresses.values():
            if contract_address in addresses:
                return addresses

        return [contract_address]
    
    def get_withdrawal_pool_amount(self, vault: Vault) -> float:
        try:
            abi = self.get_vault_abi(vault=vault)
            vault_contract, _ = self.get_vault_contract(
                vault.network_chain,
                Web3.to_checksum_address(vault.contract_address),
                abi,
            )
            pool_amount = vault_contract.functions.getWithdrawPoolAmount().call({"from": vault.owner_wallet_address})
            # Convert from wei to standard units
            return float(pool_amount/1e6)
        except Exception as e:
            logging.error(f"Error getting withdrawal pool amount for vault {vault.contract_address}: {e}")
            return 0.0
