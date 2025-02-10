from web3 import AsyncWeb3, Web3
from web3.eth import Contract

from core import constants
from core.abi_reader import read_abi
from models.vaults import Vault
from eth_utils import keccak
from eth_account.messages import encode_defunct
import eth_keys


async def sign_and_send_transaction(
    web3: AsyncWeb3, function, args, from_address, private_key, value: int = None
):
    cnt = await web3.eth.get_transaction_count(from_address)
    # cnt = 1235
    transaction = {"from": from_address, "nonce": cnt}
    if value is not None:
        transaction["value"] = value

    tx = await function(*args).build_transaction(transaction)
    signed_tx = web3.eth.account.sign_transaction(tx, private_key)
    tx_hash = await web3.eth.send_raw_transaction(signed_tx.rawTransaction)
    receipt = await web3.eth.wait_for_transaction_receipt(tx_hash)
    return receipt


def parse_hex_to_int(hex_str, is_signed=True):
    """Parse a hexadecimal string to an integer. Assumes hex_str is without '0x' and is big-endian."""
    if is_signed:
        return int.from_bytes(bytes.fromhex(hex_str), byteorder="big", signed=True)
    else:
        return int(hex_str, 16)


def get_vault_contract(
    vault: Vault, abi_name: str = "RockOnyxDeltaNeutralVault"
) -> tuple[Contract, Web3]:
    w3 = Web3(Web3.HTTPProvider(constants.NETWORK_RPC_URLS[vault.network_chain]))

    rockonyx_delta_neutral_vault_abi = read_abi(abi_name)
    vault_contract = w3.eth.contract(
        address=vault.contract_address,
        abi=rockonyx_delta_neutral_vault_abi,
    )
    return vault_contract, w3


def get_current_pps(vault_contract: Contract, decimals=1e6):
    pps = vault_contract.functions.pricePerShare().call()
    return pps / decimals


def get_current_pps_by_block(
    vault_contract: Contract,
    block_number,
    decimals=1e6,
):
    pps = vault_contract.functions.pricePerShare().call(block_identifier=block_number)
    return pps / decimals


def get_current_tvl(vault_contract: Contract, decimals=1e6):
    tvl = vault_contract.functions.totalValueLocked().call()

    return tvl / decimals


def verify_signature(message: str, signature: str, address: str) -> bool:
    w3 = Web3()

    try:
        message_hash = encode_defunct(text=message)
        recovered_address = w3.eth.account.recover_message(
            message_hash, signature=signature
        )
        return recovered_address.lower() == address.lower()
    except Exception as e:
        print(f"Verification failed: {str(e)}")
        return False


def verify_raw_signature(message: str, signature: str, public_key: str) -> bool:
    try:
        message_hash = keccak(text=message)
        sig_bytes = bytes.fromhex(signature.removeprefix("0x"))
        pub_key = eth_keys.keys.PublicKey(bytes.fromhex(public_key.removeprefix("0x")))
        return pub_key.verify_msg_hash(message_hash, sig_bytes)
    except Exception as e:
        print(f"Raw verification failed: {str(e)}")
        return False
