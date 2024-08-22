from datetime import datetime, timedelta
from typing import List
from utils.web3_utils import parse_hex_to_int


@staticmethod
def to_tx_aumount(input_data: str):
    input_data = input_data[10:].lower()
    amount = input_data[:64]
    return float(parse_hex_to_int(amount) / 1e6)


def get_init_dates() -> List[datetime]:
    start_date = datetime(2024, 3, 1)
    end_date = datetime.now() - timedelta(days=0)

    date_list = []
    current_date = start_date

    while current_date <= end_date:
        date_list.append(current_date)
        current_date += timedelta(days=1)

    return date_list
