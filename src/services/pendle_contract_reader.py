from web3 import Web3
from web3.contract import Contract

from schemas.vault_state import DepositReceiptPendle


def get_user_deposit_receipt(vault_contract: Contract, owner_address: str):
    state = vault_contract.functions.getUserDepositReciept().call(
        {"from": Web3.to_checksum_address(owner_address)}
    )
    vault_state = DepositReceiptPendle(
        shares=state[0] / 1e6,
        deposit_amount=state[1] / 1e6,
        deposit_pt_amount=state[2] / 1e6,
        deposit_sc_amount=state[3] / 1e6,
    )
    return vault_state
