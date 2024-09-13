from datetime import datetime, timedelta
from typing import List
from core import constants
from models.vaults import Vault
from services.oracle_service import get_oracle_price
from utils.web3_utils import parse_hex_to_int
from web3 import Web3


@staticmethod
def to_tx_aumount(input_data: str):
    input_data = input_data[10:].lower()
    amount = input_data[:64]
    tokenIn = input_data[64:128]
    tokenIn = f"0x{tokenIn[24:]}"
    amount = parse_hex_to_int(amount)
    if tokenIn == constants.DAI_CONTRACT_ADDRESS:
        deposit = amount / 1e18
    else:
        deposit = amount / 1e6
    return float(deposit)


@staticmethod
def to_amount_pendle(input_data: str, block_number: int, network_chain: str):
    input_data = input_data[138:].lower()
    pt_amount = int(input_data[:64], 16) / 1e18
    usdc_amount = int(input_data[64 : 64 * 2], 16) / 1e6
    web3 = Web3(Web3.HTTPProvider(constants.NETWORK_RPC_URLS[network_chain]))
    price = get_oracle_price(web3, 8, block_number)
    total_amount = pt_amount * price + usdc_amount
    return total_amount


def get_init_dates() -> List[datetime]:
    # start_date = datetime(2024, 7, 22)
    start_date = datetime(2024, 3, 1)
    end_date = datetime.now() - timedelta(days=0)

    date_list = []
    current_date = start_date

    while current_date <= end_date:
        date_list.append(current_date)
        current_date += timedelta(days=1)

    return date_list
