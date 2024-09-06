import requests

from core import constants


class KyberSwapService:
    def __init__(self, base_url):
        self.base_url = base_url

    def get_swap_route(self, chain, token_in, token_out, amount_in, save_gas=False):
        """
        Get the swap route and estimated output for a given input amount.
        """
        url = f"{self.base_url}/{chain}/api/v1/routes"
        params = {
            "tokenIn": token_in,
            "tokenOut": token_out,
            "amountIn": amount_in,
            "saveGas": save_gas,
        }

        response = requests.get(url, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Error {response.status_code}: {response.text}")

    def get_token_price(self, chain, token_in, token_out, amount_in, save_gas=False):
        """
        Retrieve the price of token_out for a given amount_in of token_in.
        """
        try:
            route_info = self.get_swap_route(
                chain, token_in, token_out, amount_in, save_gas
            )
            amount_out = route_info["data"]["routeSummary"]["amountOut"]
            return int(amount_out)
        except Exception as e:
            print(f"Failed to get token price: {e}")
            return None


# Example usage
if __name__ == "__main__":
    # Define the API base URL and client ID
    kyberswap_service = KyberSwapService(
        base_url="https://aggregator-api.kyberswap.com"
    )

    # Define parameters
    chain = "arbitrum"  # Example: ethereum, arbitrum, etc.
    token_in = constants.WETH_ADDRESS[constants.CHAIN_ARBITRUM]  # Native ETH
    token_out = constants.USDC_ADDRESS[constants.CHAIN_ARBITRUM]  # DAI
    amount_in = str(int(0.01017804369015912 * 1e18))

    # Get the price of the token_out
    price_info = kyberswap_service.get_token_price(
        chain, token_in, token_out, amount_in
    )

    if price_info:
        print(f"Amount Out: {price_info}")
