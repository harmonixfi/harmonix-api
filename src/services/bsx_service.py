
import requests
from core.config import settings

api_key = settings.BSX_API_KEY
secret = settings.BSX_SECRET
url = settings.BSX_API_URL

def get_points_earned() ->float:
    headers = {
        'accept': 'application/json',
        'accept-language': 'en-US,en;q=0.9,vi;q=0.8',   
         
        'bsx-key': api_key,
        'bsx-secret': secret,
        'cache-control': 'no-cache',
        'origin': 'https://www.testnet.bsx.exchange',
        'pragma': 'no-cache',
        'priority': 'u=1, i',
        'referer': 'https://www.testnet.bsx.exchange/',
        'sec-ch-ua': '"Not)A;Brand";v="99", "Microsoft Edge";v="127", "Chromium";v="127"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0'
    }
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        total = data.get("total_points_earned")
        return float(total) if total is not None else 0.0
    else:
        raise Exception(f"Request failed with status {response.status_code}")
    
    




