# import dependencies
import asyncio
import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Optional
import uuid

import click
from hexbytes import HexBytes
import seqlog
from sqlmodel import select
from sqlmodel import Session
from web3 import Web3
from web3._utils.filters import AsyncFilter
from websockets import ConnectionClosedError, ConnectionClosedOK

from core import constants
from core.config import settings
from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models import (
    PositionStatus,
    PricePerShareHistory,
    Transaction,
    UserPortfolio,
    Vault,
)
from models.vaults import NetworkChain, VaultCategory
from services.kyberswap import KyberSwapService
from services.socket_manager import WebSocketManager
from services.vault_contract_service import VaultContractService
from utils.calculate_price import calculate_avg_entry_price


# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

chain_name = None


def update_tvl(session: Session, vault: Vault, deposit_amount: float):
    if vault.tvl is None:
        vault.tvl = 0.0

    vault.tvl += deposit_amount
    logger.info(f"TVL updated for vault {vault.name} {vault.tvl}")
    session.add(vault)
    session.commit()


def _extract_stablecoin_event(entry):
    # Decode the data field
    data = entry["data"].hex()
    value = int(data[2:66], 16) / 1e6
    shares = int("0x" + data[66:], 16) / 1e6

    from_address = None
    if len(entry["topics"]) >= 2:
        from_address = f'0x{entry["topics"][1].hex()[26:]}'  # For deposit event
    return value, shares, from_address


def _extract_solv_event(entry):
    # Decode the data field
    data = entry["data"].hex()
    value = int(data[2:66], 16) / 1e8
    shares = int("0x" + data[66:], 16) / 1e18

    from_address = None
    if len(entry["topics"]) >= 2:
        from_address = f'0x{entry["topics"][1].hex()[26:]}'  # For deposit event
    return value, shares, from_address


def _extract_delta_neutral_event(entry):
    # Parse the account parameter from the topics field
    from_address = None
    if len(entry["topics"]) >= 2:
        from_address = f'0x{entry["topics"][1].hex()[26:]}'  # For deposit event

    # token_in = None
    # if len(entry["topics"]) >= 3:
    #     token_in = f'0x{entry["topics"][2].hex()[26:]}'

    # Parse the amount and shares parameters from the data field
    data = entry["data"].hex()
    amount = int(data[2:66], 16)

    amount = amount / 1e18 if len(str(amount)) >= 18 else amount / 1e6

    shares = int(data[66 : 66 + 64], 16) / 1e6
    return amount, shares, from_address


def _extract_pendle_event(entry):
    # Parse the account parameter from the topics field
    from_address = None
    if len(entry["topics"]) >= 2:
        from_address = f'0x{entry["topics"][1].hex()[26:]}'  # For deposit event

    # token_in = None
    # if len(entry["topics"]) >= 3:
    #     token_in = f'0x{entry["topics"][2].hex()[26:]}'

    # Parse the amount and shares parameters from the data field
    data = entry["data"].hex()
    logger.info("Raw data: %s", data)

    if entry["topics"][0].hex() == settings.PENDLE_COMPLETE_WITHDRAW_EVENT_TOPIC:
        pt_amount = int(data[2:66], 16) / 1e18
        sc_amount = int(data[66 : 66 + 64], 16) / 1e6
        shares = int(data[66 + 64 : 66 + 2 * 64], 16) / 1e6
        total_amount = int(data[66 + 2 * 64 : 66 + 3 * 64], 16) / 1e6
        eth_amount = 0
    else:
        pt_amount = int(data[2:66], 16) / 1e18
        eth_amount = int(data[66 : 66 + 64], 16) / 1e18
        sc_amount = int(data[66 + 64 : 66 + 2 * 64], 16) / 1e6
        total_amount = int(data[66 + 64 * 2 : 66 + 3 * 64], 16) / 1e6
        shares = int(data[66 + 3 * 64 : 66 + 4 * 64], 16) / 1e6
        logger.info(
            f"pt_amount: {pt_amount}, eth_amount: {eth_amount}, sc_amount: {sc_amount}, total_amount: {total_amount}, shares: {shares}"
        )

    return pt_amount, eth_amount, sc_amount, total_amount, shares, from_address


def handle_deposit_event(
    session: Session,
    user_portfolio: Optional[UserPortfolio],
    value,
    from_address,
    vault: Vault,
    latest_pps,
    shares,
    *args,
    **kwargs,
):
    if user_portfolio is None:
        logger.info(
            f"User deposit {from_address} amount = {value} at pps = {latest_pps}"
        )
        # Create new user_portfolio for this user address
        user_portfolio = UserPortfolio(
            vault_id=vault.id,
            user_address=from_address,
            total_balance=value,
            init_deposit=value,
            entry_price=latest_pps,
            pnl=0,
            status=PositionStatus.ACTIVE,
            trade_start_date=datetime.now(timezone.utc),
            total_shares=shares,
        )
        session.add(user_portfolio)
        logger.info(f"User with address {from_address} added to user_portfolio table")
    else:

        logger.info(f"User position before update {user_portfolio}")
        # Update the user_portfolio
        user_portfolio.total_balance += value
        user_portfolio.init_deposit += value
        user_portfolio.entry_price = calculate_avg_entry_price(
            user_portfolio, latest_pps, value
        )
        user_portfolio.total_shares += shares
        session.add(user_portfolio)
        logger.info(f"User deposit {from_address}, amount = {value}, shares = {shares}")
        logger.info(f"User with address {from_address} updated in user_portfolio table")

    session.commit()
    # Update TVL realtime when user deposit to vault
    update_tvl(session, vault, float(value))

    return user_portfolio


def handle_initiate_withdraw_event(
    session: Session,
    user_portfolio: UserPortfolio,
    value,
    from_address,
    shares,
    latest_pps,
    *args,
    **kwargs,
):
    if user_portfolio is not None:
        logger.info(
            f"User initiate withdrawal {from_address} amount = {value}, shares = {shares}"
        )
        if user_portfolio.pending_withdrawal is None:
            user_portfolio.pending_withdrawal = shares
        else:
            user_portfolio.pending_withdrawal += shares

        user_portfolio.init_deposit -= (
            value
            if user_portfolio.init_deposit >= value
            else user_portfolio.init_deposit
        )
        user_portfolio.initiated_withdrawal_at = datetime.now(timezone.utc)
        session.add(user_portfolio)
        session.commit()
        logger.info(f"User with address {from_address} updated in user_portfolio table")
        return user_portfolio
    else:
        logger.info(
            f"User with address {from_address} not found in user_portfolio table"
        )


def handle_withdrawn_event(
    session: Session,
    user_portfolio: UserPortfolio,
    value,
    from_address,
    vault: Vault,
    *args,
    **kwargs,
):
    if user_portfolio is not None:
        logger.info(f"User complete withdrawal {from_address} {value}")
        # user_portfolio.total_balance -= value
        vault_contract_service = VaultContractService()

        abi_name, decimals = vault_contract_service.get_vault_abi(vault=vault)

        vault_contract, _ = vault_contract_service.get_vault_contract(
            vault.network_chain, vault.contract_address, abi_name
        )

        shares = vault_contract.functions.balanceOf(
            Web3.to_checksum_address(user_portfolio.user_address)
        ).call()
        price_per_share = vault_contract.functions.pricePerShare().call()

        if vault.slug == constants.SOLV_VAULT_SLUG:
            shares = shares / 1e18
        else:
            shares = shares / decimals
        price_per_share = price_per_share / decimals
        user_portfolio.total_balance = price_per_share * shares

        # Update the pending_withdrawal, we don't allow user to withdraw more or less than pending_withdrawal
        user_portfolio.pending_withdrawal = 0
        user_portfolio.initiated_withdrawal_at = None

        if user_portfolio.total_balance <= 0:
            user_portfolio.status = PositionStatus.CLOSED
            user_portfolio.trade_end_date = datetime.now(timezone.utc)

        session.add(user_portfolio)
        session.commit()

        update_tvl(session, vault, (-1) * float(value))

        logger.info(f"User with address {from_address} updated in user_portfolio table")
        return user_portfolio
    else:
        logger.info(
            f"User with address {from_address} not found in user_portfolio table"
        )


event_handlers = {
    "Deposit": handle_deposit_event,
    "InitiateWithdraw": handle_initiate_withdraw_event,
    "Withdrawn": handle_withdrawn_event,
}


def handle_event(session: Session, vault_address: str, entry, event_name):
    # Get the vault with ROCKONYX_ADDRESS
    vault = session.exec(
        select(Vault).where(Vault.contract_address == vault_address)
    ).first()

    if vault is None:
        raise ValueError("Vault not found")

    transaction = session.exec(
        select(Transaction).where(Transaction.txhash == entry["transactionHash"])
    ).first()
    if transaction is None:
        transaction = Transaction(
            txhash=entry["transactionHash"],
        )
        session.add(transaction)
    else:
        logger.info(
            f"Transaction with txhash {entry['transactionHash']} already exists"
        )
    logger.info(f"Processing event {event_name} for vault {vault_address} {vault.name}")

    # Get the latest pps from pps_history table
    latest_pps = session.exec(
        select(PricePerShareHistory)
        .where(PricePerShareHistory.vault_id == vault.id)
        .order_by(PricePerShareHistory.datetime.desc())
    ).first()
    if latest_pps is not None:
        latest_pps = latest_pps.price_per_share
    else:
        latest_pps = 1

    # Extract the value, shares and from_address from the event
    if vault.strategy_name == constants.OPTIONS_WHEEL_STRATEGY:
        value, shares, from_address = _extract_stablecoin_event(entry)
    elif vault.strategy_name == constants.DELTA_NEUTRAL_STRATEGY:
        value, shares, from_address = _extract_delta_neutral_event(entry)
    elif vault.slug == constants.SOLV_VAULT_SLUG:
        value, shares, from_address = _extract_solv_event(entry)
        latest_pps = round(value / shares, 4)
    elif vault.strategy_name == constants.PENDLE_HEDGING_STRATEGY:
        _, eth_amount, sc_amount, value, shares, from_address = _extract_pendle_event(
            entry
        )
        logger.info(
            "Recieving data from pendle vault: %s, %s, %s from %s",
            eth_amount,
            sc_amount,
            shares,
            from_address,
        )
    else:
        raise ValueError("Invalid vault address")

    logger.info(f"Value: {value}, from_address: {from_address}")

    # Check if user with from_address has position in user_portfolio table
    user_portfolio = session.exec(
        select(UserPortfolio)
        .where(UserPortfolio.user_address == from_address)
        .where(UserPortfolio.vault_id == vault.id)
        .where(UserPortfolio.status == PositionStatus.ACTIVE)
    ).first()

    # Call the appropriate handler based on the event name
    handler = event_handlers[event_name]
    user_portfolio = handler(
        session,
        user_portfolio,
        value,
        from_address,
        vault=vault,
        shares=shares,
        latest_pps=latest_pps,
    )

    session.commit()


EVENT_FILTERS = {
    settings.STABLECOIN_DEPOSIT_VAULT_FILTER_TOPICS: {
        "event": "Deposit",
    },
    settings.STABLECOIN_INITIATE_WITHDRAW_VAULT_FILTER_TOPICS: {
        "event": "InitiateWithdraw",
    },
    settings.STABLECOIN_COMPLETE_WITHDRAW_VAULT_FILTER_TOPICS: {
        "event": "Withdrawn",
    },
    settings.DELTA_NEUTRAL_DEPOSIT_EVENT_TOPIC: {
        "event": "Deposit",
    },
    settings.MULTIPLE_STABLECOINS_DEPOSIT_EVENT_TOPIC: {
        "event": "Deposit",
    },
    settings.DELTA_NEUTRAL_INITIATE_WITHDRAW_EVENT_TOPIC: {
        "event": "InitiateWithdraw",
    },
    settings.DELTA_NEUTRAL_COMPLETE_WITHDRAW_EVENT_TOPIC: {
        "event": "Withdrawn",
    },
    settings.SOLV_DEPOSIT_EVENT_TOPIC: {
        "event": "Deposit",
    },
    settings.SOLV_INITIATE_WITHDRAW_EVENT_TOPIC: {
        "event": "InitiateWithdraw",
    },
    settings.SOLV_COMPLETE_WITHDRAW_EVENT_TOPIC: {
        "event": "Withdrawn",
    },
    settings.PENDLE_DEPOSIT_EVENT_TOPIC: {
        "event": "Deposit",
    },
    settings.PENDLE_FORCE_REQUEST_FUND_EVENT_TOPIC: {
        "event": "InitiateWithdraw",
    },
    settings.PENDLE_REQUEST_FUND_EVENT_TOPIC: {
        "event": "InitiateWithdraw",
    },
    settings.PENDLE_COMPLETE_WITHDRAW_EVENT_TOPIC: {
        "event": "Withdrawn",
    },
}


class Web3Listener(WebSocketManager):
    def __init__(self, connection_url):
        super().__init__(connection_url, logger=logger)

    async def _process_new_entries(
        self, vault_address: str, event_filter: AsyncFilter, event_name: str
    ):
        events = await event_filter.get_new_entries()
        for event in events:
            handle_event(vault_address, event, event_name)

    async def listen_for_events(self, network: NetworkChain):
        while True:
            try:
                with Session(engine) as session:
                    # query all active vaults
                    vaults = session.exec(
                        select(Vault)
                        .where(Vault.is_active == True)
                        .where(Vault.network_chain == network)
                        .where(Vault.category != VaultCategory.real_yield_v2)
                    ).all()
                    logger.info("Subcribing to %d vaults...", len(vaults))

                    for vault in vaults:
                        # subscribe to new block headers
                        subscription_id = await self.w3.eth.subscribe(
                            "logs",
                            {
                                "address": vault.contract_address,
                            },
                        )
                        logger.info(
                            "Subscription %s - %s response: %s",
                            vault.name,
                            vault.contract_address,
                            subscription_id,
                        )

                    async for msg in self.read_messages():
                        logger.info("Received message: %s", msg)
                        # Handle the event
                        # await self.handle_events()
                        res = msg["result"]
                        if res["topics"][0].hex() in EVENT_FILTERS.keys():
                            event_filter = EVENT_FILTERS[res["topics"][0].hex()]
                            handle_event(
                                session, res["address"], res, event_filter["event"]
                            )
            except (ConnectionClosedError, ConnectionClosedOK) as e:
                self.logger.error("Websocket connection close", exc_info=True)
                self.logger.error(traceback.format_exc())
                await asyncio.sleep(2)
                await self.reconnect()
                # raise e
            except Exception as e:
                logger.error(f"Error: {e}")
                logger.error(traceback.format_exc())

    async def run(self, network: NetworkChain):
        await self.connect()

        try:
            await self.listen_for_events(network)
        except Exception as e:
            logger.error(f"Error: {e}")
            logger.error(traceback.format_exc())
        finally:
            await self.disconnect()


async def run(network: str):
    global chain_name
    logger.info("Starting web3 listener for %s", network)

    # Parse network to NetworkChain enum
    network_chain = NetworkChain[network.lower()]
    chain_name = network.lower()

    # Select connection_url based on network_chain
    if network_chain == NetworkChain.arbitrum_one:
        connection_url = settings.ARBITRUM_MAINNET_INFURA_WEBSOCKER_URL
    elif network_chain == NetworkChain.ethereum:
        connection_url = settings.ETHER_MAINNET_INFURA_WEBSOCKER_URL
    elif network_chain == NetworkChain.base:
        connection_url = settings.BASE_MAINNET_WSS_NETWORK_RPC
    else:
        raise ValueError(f"Unsupported network: {network}")

    web3_listener = Web3Listener(connection_url)
    await web3_listener.run(network)


def test():
    from web3.datastructures import AttributeDict

    msg = {
        "subscription": "0x29ddee6dde05ff956da4dc54234e80bb",
        "result": AttributeDict(
            {
                "address": "0x9d95527A298c68526Ad5227fe241B75329D3b91F",
                "topics": [
                    HexBytes(
                        "0x92ccf450a286a957af52509bc1c9939d1a6a481783e142e41e2499f0bb66ebc6"
                    ),
                    HexBytes(
                        "0x000000000000000000000000d8c1aaa863c7251a0603b4905eac0d37eaf91f63"
                    ),
                ],
                "data": HexBytes(
                    "0x00000000000000000000000000000000000000000000000000000000001e9f1e00000000000000000000000000000000000000000000000000400a8d2eb89fce"
                ),
                "blockNumber": 295679459,
                "transactionHash": HexBytes(
                    "0x175915f1568914e1397d16747814f102fb92259f194e8db1a6b19aba6947ab68"
                ),
                "transactionIndex": 3,
                "blockHash": HexBytes(
                    "0x0c62efb7a1117351b369aa1ae058c34af9bcb359f4ac8ab69d4ae8b7f49c52c5"
                ),
                "logIndex": 13,
                "removed": False,
            }
        ),
    }
    with Session(engine) as session:
        res = msg["result"]
        if res["topics"][0].hex() in EVENT_FILTERS.keys():
            event_filter = EVENT_FILTERS[res["topics"][0].hex()]
            handle_event(session, res["address"], res, event_filter["event"])


@click.command()
@click.option("--network", default="arbitrum_one", help="Blockchain network to use")
def main(network: str):
    setup_logging_to_console()
    setup_logging_to_file(
        app=f"web3_listener_{network}", level=logging.INFO, logger=logger
    )
    asyncio.run(run(network))
    # test()


if __name__ == "__main__":
    main()
