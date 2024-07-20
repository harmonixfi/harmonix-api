from datetime import datetime, timezone
from typing import Any, List, Tuple
from sqlmodel import Session, select
from web3 import Web3
from core import constants
from core.abi_reader import read_abi
from core.config import settings
from core.db import engine
from models.onchain_transaction_history import OnchainTransactionHistory
from models.user_assets_history import UserHoldingAssetHistory
from schemas.vault_state import OldVaultState, VaultState
from services.uniswap_pool_service import Uniswap


OWNER = "0x0d4eef21D898883a6bd1aE518B60fEf7A951ce4D"

rockonyx_delta_neutral_vault_abi = read_abi("rockonyxrestakingdeltaneutralvault")
erc20_abi = read_abi("erc20")


def get_pps(vault_contract, block_number: int) -> float:
    pps = vault_contract.functions.pricePerShare().call(block_identifier=block_number)
    return pps / 1e6


def get_user_shares(vault_contract, address: str, block_number: int) -> float:
    balance = vault_contract.functions.balanceOf(
        Web3.to_checksum_address(address)
    ).call(block_identifier=block_number)
    return balance / 1e6


def get_total_shares(vault_contract, vault_address: str, block_number: int) -> float:
    state = vault_contract.functions.getVaultState().call(
        {"from": Web3.to_checksum_address(OWNER)}, block_identifier=block_number
    )

    if (
        vault_address.lower() in {"0x2b7cdad36a86fd05ac1680cdc42a0ea16804d80c", "0xf30353335003e71b42a89314aaaec437e7bc8f0b"}
    ):  # this contract using old state definition struct
        vault_state = OldVaultState(
            performance_fee=state[0] / 1e6,
            management_fee=state[1] / 1e6,
            withdrawal_pool=state[2] / 1e6,
            pending_deposit=state[3] / 1e6,
            total_share=state[4] / 1e6,
        )
    else:
        vault_state = VaultState(
            withdraw_pool_amount=state[0] / 1e6,
            pending_deposit=state[1] / 1e6,
            total_share=state[2] / 1e6,
            total_fee_pool_amount=state[3] / 1e6,
            last_update_management_fee_date=state[4],
        )
    return vault_state.total_share


def _extract_delta_neutral_event(data):
    # Parse the amount and shares parameters from the data field
    data = data[10:]  # remove method id
    amount = int(data[0:64], 16)

    amount = amount / 1e18 if len(str(amount)) >= 18 else amount / 1e6

    shares = int(data[64 : 64 + 64], 16) / 1e6
    return amount, shares


def calculate_rseth_holding(session: Session, tx_history: Tuple[Any, str, List[OnchainTransactionHistory]]):
        user_positions = {}
        cumulative_deployment_fund = 0

        for vault_contract, vault_address, transactions in tx_history:
            print(f'--- processing {vault_address} ---\n')

            for tx in transactions:
                if tx.method_id == "0x2e2d2984":  # Deposit
                    """
                    When events happen, we need to update the current user shares in vault
                    """
                    user_shares = get_user_shares(
                        vault_contract, tx.from_address, tx.block_number
                    )
                    # pps = get_pps(tx.block_number)
                    user_deposit_amount, _ = _extract_delta_neutral_event(tx.input)
                    print(
                        f"{tx.from_address} deposited {user_deposit_amount} USDC. Shares = {user_shares} roUSD"
                    )

                    if tx.from_address not in user_positions:
                        user_positions[tx.from_address] = {
                            "shares": user_shares,
                            "deposit_amount": 0,
                        }

                    user_positions[tx.from_address] = {
                        "shares": user_shares,
                        "deposit_amount": user_positions[tx.from_address]["deposit_amount"]
                        + user_deposit_amount,
                    }

                elif tx.method_id == "0x99ff8203":  # openPosition
                    """
                    This method will actually change the rsETH in vault
                    leed to change in user holdnig as well
                    """

                    if not user_positions:
                        continue

                    print("------- // open position //----")
                    print(f"block number {tx.block_number}")

                    bought_weth_amount = int(tx.input[10:], 16) / 1e18
                    print(f"Opened position size = {bought_weth_amount:.6f} WETH")

                    eth_price = uniswap.get_price_of(WETH_ADDRESS, USDC_ADDRESS, block_number=tx.block_number) / 1e6
                    bought_weth_amount_in_usdc = bought_weth_amount * eth_price
                    cumulative_deployment_fund += bought_weth_amount_in_usdc
                    print(
                        f"Opened position size = {bought_weth_amount_in_usdc:.2f} USDC. Cumulative deployment fund = {cumulative_deployment_fund:.2f} USDC"
                    )

                    pending_deployment_fund = sum(
                        x["deposit_amount"] for x in user_positions.values()
                    ) * 0.5  # we use 50% of the deposit amount to buy spot, 50% to buy perpetual which is not considered here
                    print(f"Pending deployment fund = {pending_deployment_fund:.2f} USDC")
                    print('\n')

                    # if cumulative_deployment_fund > 95% of pending deployment fund, then we consider that the fund is fully deployed
                    # then user will be allocated rsETH to be fair with the current user in pool
                    if (
                        cumulative_deployment_fund
                        < pending_deployment_fund * 0.95
                    ):
                        continue

                    # get balanceOf rsETH
                    rseth_balance = (
                        rseth_contract.functions.balanceOf(
                            Web3.to_checksum_address(vault_address)
                        ).call(block_identifier=tx.block_number)
                        / 1e18
                    )
                    print(f"rsETH balance: {rseth_balance}")

                    vault_total_shares = get_total_shares(
                        vault_contract, vault_address, tx.block_number
                    )
                    print(f"Total shares: {vault_total_shares}")

                    # when fund is fully deployed, we need to calculate the user holding
                    for user, data in user_positions.items():
                        user_shares = data["shares"]
                        user_pool_share_pct = user_shares / vault_total_shares
                        user_rseth_holding = rseth_balance * user_pool_share_pct
                        print(
                            f"{user}, pct = {user_pool_share_pct*100:.2f} has {user_rseth_holding:.4f} rsETH"
                        )

                        # Log the change for the user into UserHistory
                        user_history = UserHoldingAssetHistory(
                            user_address=user,
                            total_shares=user_shares,
                            vault_total_shares=vault_total_shares,
                            asset_amount=user_rseth_holding,
                            asset_address=RSETH_ADDRESS,  # rsETH contract address
                            asset_symbol="rsETH",
                            asset_decimals=18,
                            holding_percentage=user_pool_share_pct,
                            timestamp=datetime.fromtimestamp(tx.timestamp, timezone.utc),
                            block_number=tx.block_number,
                        )
                        session.add(user_history)

                        user_positions[user]['deposit_amount'] = 0
                    
                    cumulative_deployment_fund = 0  # reset the deployment fund
                    session.commit()

                    print("------- // end open position //----")

                elif tx.method_id == '0x12edde5e':  # initiate withdrawal
                    print(f"User {tx.from_address} initiated withdrawal")
                
                elif tx.method_id == "0xa126d601":  # close position
                    print("------- // close position //----")
                    print(f"block number {tx.block_number}")
                    print(f"tx hash {tx.tx_hash}")

                    # get balanceOf rsETH
                    rseth_balance = (
                        rseth_contract.functions.balanceOf(
                            Web3.to_checksum_address(vault_address)
                        ).call(block_identifier=tx.block_number)
                        / 1e18
                    )
                    print(f"rsETH balance: {rseth_balance}")

                    vault_total_shares = get_total_shares(
                        vault_contract, vault_address, tx.block_number
                    )
                    print(f"Total shares: {vault_total_shares}")

                    # when fund is fully deployed, we need to calculate the user holding
                    for user, data in user_positions.items():
                        user_shares = data["shares"]
                        user_pool_share_pct = user_shares / vault_total_shares
                        user_rseth_holding = rseth_balance * user_pool_share_pct
                        print(
                            f"{user}, pct = {user_pool_share_pct*100:.2f} has {user_rseth_holding:.4f} rsETH"
                        )

                        # Log the change for the user into UserHistory
                        user_history = UserHoldingAssetHistory(
                            user_address=user,
                            total_shares=user_shares,
                            vault_total_shares=vault_total_shares,
                            asset_amount=user_rseth_holding,
                            asset_address=RSETH_ADDRESS,  # rsETH contract address
                            asset_symbol="rsETH",
                            asset_decimals=18,
                            holding_percentage=user_pool_share_pct,
                            timestamp=datetime.fromtimestamp(tx.timestamp, timezone.utc),
                            block_number=tx.block_number,
                        )
                        session.add(user_history)
                    
                    print("------- // END close position //----")


def _create_vault_contract(vault_address: str, chain: str):
    vault_address = Web3.to_checksum_address(vault_address)
    vault_contract = w3.eth.contract(
        address=vault_address,
        abi=rockonyx_delta_neutral_vault_abi,
    )
    return vault_contract


kelpdao_vaults = [
    {
        "address": "0x2b7cdad36a86fd05ac1680cdc42a0ea16804d80c",
        "chain": constants.CHAIN_ARBITRUM,
    },
    {
        "address": "0xF30353335003E71b42a89314AAaeC437E7Bc8F0B",
        "chain": constants.CHAIN_ARBITRUM,
    },
    {
        "address": "0x4a10C31b642866d3A3Df2268cEcD2c5B14600523",
        "chain": constants.CHAIN_ARBITRUM,
    },
]

w3: Web3 = None

RSETH_ADDRESS = None
WETH_ADDRESS = None
USDC_ADDRESS = None

rseth_contract = None
weth_contract = None

uniswap: Uniswap = None


def main(chain):
    global w3, rseth_contract, weth_contract, uniswap, RSETH_ADDRESS, WETH_ADDRESS, USDC_ADDRESS

    if chain == constants.CHAIN_ARBITRUM:
        w3 = Web3(Web3.HTTPProvider(settings.ARBITRUM_MAINNET_INFURA_URL))
    elif chain == constants.CHAIN_ETHER_MAINNET:
        w3 = Web3(Web3.HTTPProvider(settings.ETHER_MAINNET_INFURA_URL))
    else:
        raise Exception("Chain not supported")

    RSETH_ADDRESS = constants.RSETH_ADDRESS[chain]
    WETH_ADDRESS = constants.WETH_ADDRESS[chain]
    USDC_ADDRESS = constants.USDC_ADDRESS[chain]

    rseth_contract = w3.eth.contract(address=RSETH_ADDRESS, abi=erc20_abi)
    weth_contract = w3.eth.contract(address=WETH_ADDRESS, abi=erc20_abi)

    uniswap = Uniswap(w3, chain)

    with Session(engine) as session:
        tx_history = []

        for vault in kelpdao_vaults:
            vault_address = vault["address"]
            chain = vault["chain"]

            vault_contract = _create_vault_contract(vault_address, chain)

            # fetch all OnchainTransactionHistory order by block_number asc
            transactions = session.exec(
                select(OnchainTransactionHistory)
                .where(OnchainTransactionHistory.to_address == vault_address.lower())
                .order_by(OnchainTransactionHistory.block_number.asc())
            ).all()

            tx_history.append((vault_contract, vault_address, transactions))
        
        calculate_rseth_holding(session, tx_history)


if __name__ == "__main__":
    main(constants.CHAIN_ARBITRUM)
