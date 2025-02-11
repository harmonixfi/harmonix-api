import requests
from core.config import settings

url = settings.VALIDAO_URL
referral_code = settings.VALIDAO_REFERRAL_CODE
api_key = settings.PARTNER_VALIDAO_API_KEY


def stake(
    chain_id: str,
    user_address: str,
    stake_amount: float,
    transation_id: str,
):
    params = {
        "chainId": chain_id,
        "delegatorAddress": user_address,
        "delegatedAmount": stake_amount,
        "transactionId": transation_id,
    }
    headers = {"Authorization": api_key, "Content-Type": "application/json"}

    try:
        response = requests.post(
            f"{url}/api/partner/stake?referralCode={referral_code}",
            headers=headers,
            params=params,
        )
        response.raise_for_status()  # Raise HTTPError for bad responses

        return response.json()

    except requests.RequestException as e:
        print(f"Error fetching funding history: {e}")
        return []
