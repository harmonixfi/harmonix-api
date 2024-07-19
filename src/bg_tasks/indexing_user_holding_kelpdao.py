from datetime import datetime, timezone
from sqlmodel import Session, select
from web3 import Web3
from core.abi_reader import read_abi
from core.config import settings
from core.db import engine
from models.onchain_transaction_history import OnchainTransactionHistory
from models.user_assets_history import UserHoldingAssetHistory
from schemas.vault_state import OldVaultState, VaultState


w3 = Web3(Web3.HTTPProvider(settings.ARBITRUM_MAINNET_INFURA_URL))

OWNER = "0x0d4eef21D898883a6bd1aE518B60fEf7A951ce4D"

rockonyx_delta_neutral_vault_abi = read_abi("rockonyxrestakingdeltaneutralvault")

erc20_abi = read_abi("erc20")

RSETH_ADDRESS = "0x4186BFC76E2E237523CBC30FD220FE055156b41F"
rseth_contract = w3.eth.contract(address=RSETH_ADDRESS, abi=erc20_abi)


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
        vault_address.lower() == "0x2b7cdad36a86fd05ac1680cdc42a0ea16804d80c"
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


def calculate_rseth_holding(vault_contract, vault_address: str):
    with Session(engine) as session:
        # fetch all OnchainTransactionHistory order by block_number asc
        transactions = session.exec(
            select(OnchainTransactionHistory)
            .where(OnchainTransactionHistory.to_address == vault_address.lower())
            .order_by(OnchainTransactionHistory.block_number.asc())
        )

        user_positions = {}

        for tx in transactions:
            if tx.method_id in {
                "0x2e2d2984",
                "0x12edde5e",
            }:  # Deposit, InitiateWithdraw
                """
                When events happen, we need to update the current user shares in vault
                """
                user_shares = get_user_shares(
                    vault_contract, tx.from_address, tx.block_number
                )
                # pps = get_pps(tx.block_number)
                # user_deposit_amount = user_shares * pps
                print(f"{tx.from_address} deposited {user_shares} roUSD")

                if tx.from_address not in user_positions:
                    user_positions[tx.from_address] = 0

                user_positions[tx.from_address] = user_shares

            elif tx.method_id in {
                "0x99ff8203",
                "0xa126d601",
            }:  # openPosition, closePosition
                """
                This method will actually change the rsETH in vault
                leed to change in user holdnig as well
                """

                if not user_positions:
                    continue

                print("------- // open position //----")
                print(f"block number {tx.block_number}")
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

                for user, user_shares in user_positions.items():
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

                session.commit()

                print("------- // end open position //----")


def _create_vault_contract(vault_address: str):
    vault_address = Web3.to_checksum_address(vault_address)
    vault_contract = w3.eth.contract(
        address=vault_address,
        abi=rockonyx_delta_neutral_vault_abi,
    )
    return vault_contract


kelpdao_vaults = [
    {
        "address": "0x2b7cdad36a86fd05ac1680cdc42a0ea16804d80c",
    },
    {
        "address": "0x4a10C31b642866d3A3Df2268cEcD2c5B14600523",
    },
]


if __name__ == "__main__":

    for vault in kelpdao_vaults:
        vault_address = vault["address"]
        vault_contract = _create_vault_contract(vault_address)
        calculate_rseth_holding(vault_contract, vault_address)
    # get_user_shares("0x8737AcdA55a43aCccF7Ed4A3818663D921ef826b", 216998166)
