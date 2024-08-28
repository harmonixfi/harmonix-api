# import dependencies
import asyncio
import logging
import traceback

import click
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
    Vault,
)
from models.vaults import NetworkChain
from notifications import telegram_bot
from notifications.message_builder import build_message
from services.socket_manager import WebSocketManager
from utils.calculate_price import calculate_avg_entry_price


# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

chain_name = None

session = Session(engine)


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


async def handle_event(vault_address: str, entry, event_name):
    # Get the vault with ROCKONYX_ADDRESS
    vault = session.exec(
        select(Vault).where(Vault.contract_address == vault_address)
    ).first()

    if vault is None:
        raise ValueError("Vault not found")

    logger.info(f"Processing event {event_name} for vault {vault_address} {vault.name}")

    # Extract the value, shares and from_address from the event
    if vault.strategy_name == constants.OPTIONS_WHEEL_STRATEGY:
        value, shares, from_address = _extract_stablecoin_event(entry)
    elif vault.strategy_name == constants.DELTA_NEUTRAL_STRATEGY:
        value, shares, from_address = _extract_delta_neutral_event(entry)
    elif vault.slug == constants.SOLV_VAULT_SLUG:
        value, shares, from_address = _extract_solv_event(entry)
    else:
        raise ValueError("Invalid vault address")

    logger.info(f"Value: {value}, from_address: {from_address}")

    event_name_send_bot = event_name
    if event_name == "InitiateWithdraw":
        event_name_send_bot = "Initiate Withdrawals"
    if event_name == "Withdrawn":
        event_name_send_bot == "Complete Withdraw"

    try:
        await telegram_bot.send_alert(
            build_message(
                fields=[
                    ["Event", event_name_send_bot],
                    ["Strategy", vault.name],
                    ["Contract", vault_address],
                    ["Value", value],
                ]
            ),
            channel="transaction",
        )
    except Exception as e:
        logger.error(f"Failed to send alert: {e}")


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
}


class MonitoringListener(WebSocketManager):
    def __init__(self, connection_url):
        super().__init__(connection_url, logger=logger)

    async def _process_new_entries(
        self, vault_address: str, event_filter: AsyncFilter, event_name: str
    ):
        events = await event_filter.get_new_entries()
        for event in events:
            await handle_event(vault_address, event, event_name)

    async def listen_for_events(self, network: NetworkChain):
        while True:
            try:
                # query all active vaults
                vaults = session.exec(
                    select(Vault)
                    .where(Vault.is_active == True)
                    .where(Vault.network_chain == network)
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
                        await handle_event(res["address"], res, event_filter["event"])
            except (ConnectionClosedError, ConnectionClosedOK) as e:
                self.logger.error("Websocket connection close", exc_info=True)
                self.logger.error(traceback.format_exc())
                raise e
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

    monitoring_listener = MonitoringListener(connection_url)
    await monitoring_listener.run(network)


@click.command()
@click.option("--network", default="arbitrum_one", help="Blockchain network to use")
def main(network: str):
    setup_logging_to_console()
    setup_logging_to_file(
        app=f"monitoring_listener{network}", level=logging.INFO, logger=logger
    )
    asyncio.run(run(network))


if __name__ == "__main__":
    main()
