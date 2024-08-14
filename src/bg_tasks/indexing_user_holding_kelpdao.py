from datetime import datetime, timezone
import json
import logging
import os
import pprint
from typing import Any, List, Tuple
import click
from sqlmodel import Session, select
from web3 import Web3
from core import constants
from core.abi_reader import read_abi
from core.config import settings
from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models.onchain_transaction_history import OnchainTransactionHistory
from models.user_assets_history import UserHoldingAssetHistory
from models.vaults import Vault
from schemas.vault_state import OldVaultState, VaultState
from services.uniswap_pool_service import Uniswap

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


rockonyx_delta_neutral_vault_abi = read_abi("rockonyxrestakingdeltaneutralvault")
erc20_abi = read_abi("erc20")

STATE_ROOT_PATH = "/api-data/kelpdao"
STATE_FILE_PATH = STATE_ROOT_PATH + "/{0}_state.json"


def save_state(vault_address, user_positions, cumulative_deployment_fund, latest_block):
    state = {
        "user_positions": user_positions,
        "cumulative_deployment_fund": cumulative_deployment_fund,
        "latest_block": latest_block,
    }

    filename = STATE_FILE_PATH.format(vault_address)

    backup_path = f"{STATE_ROOT_PATH}/{vault_address}_state_{latest_block}.json"
    if not os.path.exists(STATE_ROOT_PATH):
        # Create the path
        os.makedirs(STATE_ROOT_PATH)
        logger.info(f"Directory {STATE_ROOT_PATH} created.")

    # copy filename to backup_path
    if os.path.exists(filename):
        os.system(f"cp {filename} {backup_path}")

    with open(filename, "w") as f:
        json.dump(state, f)


def load_state(vault_address: str):
    filename = STATE_FILE_PATH.format(vault_address)
    if not os.path.exists(filename):
        return {}, 0, 0

    with open(filename, "r") as f:
        state = json.load(f)

    return (
        state["user_positions"],
        state["cumulative_deployment_fund"],
        state["latest_block"],
    )


def get_pps(vault_contract, block_number: int) -> float:
    pps = vault_contract.functions.pricePerShare().call(block_identifier=block_number)
    return pps / 1e6


def get_user_shares(vault_contract, address: str, block_number: int) -> float:
    balance = vault_contract.functions.balanceOf(
        Web3.to_checksum_address(address)
    ).call(block_identifier=block_number)
    return balance / 1e6


def get_total_shares(
    vault_contract, vault_address: str, block_number: int, admin_wallet: str
) -> float:
    state = vault_contract.functions.getVaultState().call(
        {"from": Web3.to_checksum_address(admin_wallet)}, block_identifier=block_number
    )

    if vault_address.lower() in {
        "0x2b7cdad36a86fd05ac1680cdc42a0ea16804d80c",
        "0xf30353335003e71b42a89314aaaec437e7bc8f0b",
    }:  # this contract using old state definition struct
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


def get_rseth_balance(chain, vault_address, block_number):
    if chain == constants.CHAIN_ARBITRUM:
        rseth_balance = (
            rseth_contract.functions.balanceOf(
                Web3.to_checksum_address(vault_address)
            ).call(block_identifier=block_number)
            / 1e18
        )
    elif chain == constants.CHAIN_ETHER_MAINNET:
        zircuit_contract = w3.eth.contract(
            address=constants.ZIRCUIT_DEPOSIT_CONTRACT_ADDRESS,
            abi=constants.ZIRCUIT_ABI,
        )
        rseth_balance = (
            zircuit_contract.functions.balance(RSETH_ADDRESS, vault_address).call(
                block_identifier=block_number
            )
            / 1e18
        )
    else:
        raise ValueError(f"Unsupported chain: {chain}")
    return rseth_balance


def calculate_rseth_holding(
    session: Session,
    tx_history: Tuple[Any, str, List[OnchainTransactionHistory]],
    user_positions: dict = {},
    cumulative_deployment_fund: float = 0,
    latest_block: float = 0,
    chain: str = constants.CHAIN_ARBITRUM,
):
    for vault_contract, vault_address, vault_admin, transactions in tx_history:
        logger.info(f"--- processing {vault_address} ---\n")

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
                logger.info(
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

                logger.info("------- // open position //----")
                logger.info(f"block number {tx.block_number}")

                bought_weth_amount = int(tx.input[10:], 16) / 1e18
                logger.info(f"Opened position size = {bought_weth_amount:.6f} WETH")

                eth_price = (
                    uniswap.get_price_of(
                        WETH_ADDRESS, USDC_ADDRESS, block_number=tx.block_number
                    )
                    / 1e6
                )
                bought_weth_amount_in_usdc = bought_weth_amount * eth_price
                cumulative_deployment_fund += bought_weth_amount_in_usdc
                logger.info(
                    f"Opened position size = {bought_weth_amount_in_usdc:.2f} USDC. Cumulative deployment fund = {cumulative_deployment_fund:.2f} USDC"
                )

                pending_deployment_fund = (
                    sum(x["deposit_amount"] for x in user_positions.values()) * 0.5
                )  # we use 50% of the deposit amount to buy spot, 50% to buy perpetual which is not considered here
                logger.info(
                    f"Pending deployment fund = {pending_deployment_fund:.2f} USDC"
                )
                logger.info("\n")

                # if cumulative_deployment_fund > 95% of pending deployment fund, then we consider that the fund is fully deployed
                # then user will be allocated rsETH to be fair with the current user in pool
                if cumulative_deployment_fund < pending_deployment_fund * 0.95:
                    continue

                # get balanceOf rsETH
                rseth_balance = get_rseth_balance(chain, vault_address, tx.block_number)
                logger.info(f"rsETH balance: {rseth_balance}")

                vault_total_shares = get_total_shares(
                    vault_contract, vault_address, tx.block_number, vault_admin
                )
                logger.info(f"Total shares: {vault_total_shares}")

                # when fund is fully deployed, we need to calculate the user holding
                for user, data in user_positions.items():
                    user_shares = data["shares"]
                    user_pool_share_pct = user_shares / vault_total_shares
                    user_rseth_holding = rseth_balance * user_pool_share_pct
                    logger.info(
                        f"{user}, pct = {user_pool_share_pct*100:.2f} has {user_rseth_holding:.8f} rsETH"
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
                        chain=chain,
                    )
                    session.add(user_history)

                    user_positions[user]["deposit_amount"] = 0

                cumulative_deployment_fund = 0  # reset the deployment fund
                session.commit()

                logger.info("------- // end open position //----")

            elif tx.method_id == "0x12edde5e":  # initiate withdrawal
                logger.info(f"User {tx.from_address} initiated withdrawal")

            elif tx.method_id == "0xa126d601":  # close position
                logger.info("------- // close position //----")
                logger.info(f"block number {tx.block_number}")
                logger.info(f"tx hash {tx.tx_hash}")

                # get balanceOf rsETH
                rseth_balance = get_rseth_balance(chain, vault_address, tx.block_number)
                logger.info(f"rsETH balance: {rseth_balance}")

                vault_total_shares = get_total_shares(
                    vault_contract, vault_address, tx.block_number, vault_admin
                )
                logger.info(f"Total shares: {vault_total_shares}")

                # when fund is fully deployed, we need to calculate the user holding
                for user, data in user_positions.items():
                    user_shares = data["shares"]
                    user_pool_share_pct = user_shares / vault_total_shares
                    user_rseth_holding = rseth_balance * user_pool_share_pct
                    logger.info(
                        f"{user}, pct = {user_pool_share_pct*100:.2f} has {user_rseth_holding:.8f} rsETH"
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
                        chain=chain,
                    )
                    session.add(user_history)

                logger.info("------- // END close position //----")

        if len(transactions) > 0:
            # Save state after processing each transaction
            latest_block = tx.block_number
            save_state(
                vault_address, user_positions, cumulative_deployment_fund, latest_block
            )


def _create_vault_contract(vault_address: str, chain: str):
    vault_address = Web3.to_checksum_address(vault_address)
    vault_contract = w3.eth.contract(
        address=vault_address,
        abi=rockonyx_delta_neutral_vault_abi,
    )
    return vault_contract


kelpdao_vaults = {
    "ethereum": [
        {
            "address": "0x09f2b45a6677858f016EBEF1E8F141D6944429DF",
            "admin": "0x470e1d28639B1bd5624c85235eeF29624A597E68",
            "chain": constants.CHAIN_ETHER_MAINNET,
        }
    ],
    "arbitrum_one": [
        {
            "address": "0x2b7cdad36a86fd05ac1680cdc42a0ea16804d80c",
            "admin": "0x0d4eef21D898883a6bd1aE518B60fEf7A951ce4D",
            "chain": constants.CHAIN_ARBITRUM,
        },
        {
            "address": "0xF30353335003E71b42a89314AAaeC437E7Bc8F0B",
            "admin": "0x0d4eef21D898883a6bd1aE518B60fEf7A951ce4D",
            "chain": constants.CHAIN_ARBITRUM,
        },
        {
            "address": "0x4a10C31b642866d3A3Df2268cEcD2c5B14600523",
            "admin": "0x0d4eef21D898883a6bd1aE518B60fEf7A951ce4D",
            "chain": constants.CHAIN_ARBITRUM,
        },
    ],
}

w3: Web3 = None

RSETH_ADDRESS = None
WETH_ADDRESS = None
USDC_ADDRESS = None

rseth_contract = None
weth_contract = None

uniswap: Uniswap = None


def import_historical_data(chain, vault_id: str):
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

        for vault in kelpdao_vaults[chain]:
            vault_address = vault["address"]
            chain = vault["chain"]

            vault_contract = _create_vault_contract(vault_address, chain)

            # fetch all OnchainTransactionHistory order by block_number asc
            transactions = session.exec(
                select(OnchainTransactionHistory)
                .where(OnchainTransactionHistory.to_address == vault_address.lower())
                .where(OnchainTransactionHistory.chain == chain)
                .order_by(OnchainTransactionHistory.block_number.asc())
            ).all()

            tx_history.append(
                (vault_contract, vault_address, vault["admin"], transactions)
            )

        calculate_rseth_holding(session, tx_history, chain=chain)


def import_live_data(chain, vault_id: str):
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
        vault = session.exec(select(Vault).where(Vault.id == vault_id)).first()
        if not vault:
            logger.info(f"Vault {vault_id} not found")
            return

        tx_history = []

        vault_address = vault.contract_address
        chain = vault.network_chain

        vault_contract = _create_vault_contract(vault_address, chain)

        user_positions, cumulative_deployment_fund, latest_block = load_state(
            vault.contract_address
        )
        if latest_block != 0:
            logger.info(
                f"Resuming from block {latest_block}, cumulative deployment fund = {cumulative_deployment_fund}"
            )
            logger.info(user_positions)

        # fetch all OnchainTransactionHistory order by block_number asc
        transactions = session.exec(
            select(OnchainTransactionHistory)
            .where(OnchainTransactionHistory.to_address == vault_address.lower())
            .where(OnchainTransactionHistory.block_number > latest_block)
            .where(OnchainTransactionHistory.chain == chain)
            .order_by(OnchainTransactionHistory.block_number.asc())
        ).all()

        tx_history.append(
            (vault_contract, vault_address, vault.owner_wallet_address, transactions)
        )

        calculate_rseth_holding(
            session,
            tx_history,
            user_positions=user_positions,
            cumulative_deployment_fund=cumulative_deployment_fund,
            latest_block=latest_block,
            chain=chain,
        )


@click.group()
def cli():
    pass


@cli.command()
@click.option("--chain", required=True, help="Blockchain network chain")
@click.option("--vault-id", required=True, help="Vault ID")
def live(chain, vault_id):
    setup_logging_to_console()
    setup_logging_to_file(
        f"indexing_user_holding_kelpdao_{chain}_{vault_id}", logger=logger
    )
    # Logic for live mode
    logger.info(f"Running in live mode for chain {chain} and vault ID {vault_id}")

    import_live_data(chain, vault_id)


@cli.command()
@click.option("--chain", required=True, help="Blockchain network chain")
@click.option("--vault-id", required=True, help="Vault ID")
def historical(chain, vault_id):
    # Logic for historical mode
    logger.info(f"Running in historical mode for chain {chain} and vault ID {vault_id}")
    import_historical_data(chain, vault_id)


if __name__ == "__main__":
    cli()
