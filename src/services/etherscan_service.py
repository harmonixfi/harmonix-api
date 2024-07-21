import requests
from core.config import settings

api_key = settings.ETHERSCAN_API_KEY
url = settings.ETHERSCAN_GET_TRANSACTIONS_URL


def get_transactions(
    vault_address, start_block: int, end_block: int, page=0, offset=100
):
    query_params = {
        "address": vault_address,
        "startblock": start_block,
        "endblock": end_block,
        "page": page,
        "offset": offset,
        "sort": "desc",
        "apikey": api_key,
    }
    api_url = (
        f"{url}&{'&'.join(f'{key}={value}' for key, value in query_params.items())}"
    )
    response = requests.get(api_url)
    response_json = response.json()
    transactions = response_json["result"]
    return transactions
