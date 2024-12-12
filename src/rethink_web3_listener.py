import logging
import traceback
from datetime import datetime, timezone

import asyncio
import click
from hexbytes import HexBytes
from sqlmodel import Session, select
from web3 import Web3
from web3.eth import Contract
from websockets import ConnectionClosedError, ConnectionClosedOK

from core import constants
from core.config import settings
from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models import (
    PositionStatus,
    Transaction,
    UserPortfolio,
    Vault,
)
from models.vaults import NetworkChain, VaultCategory
from services.market_data import get_price
from utils.web3_utils import get_vault_contract, get_current_pps
from web3_listener import (
    Web3Listener,
    handle_initiate_withdraw_event,
    handle_withdrawn_event,
)

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rethink_web3_listener")

session = Session(engine)

RETHINK_EVENT_FILTERS = {
    settings.RETHINK_DELTA_NEUTRAL_DEPOSIT_EVENT_TOPIC: {
        "event": "Deposit",
    },
    settings.RETHINK_DELTA_NEUTRAL_DEPOSITED_TO_FUND_CONTRACT_EVENT_TOPIC: {
        "event": "DepositedToFundContract",
    },
    settings.RETHINK_DELTA_NEUTRAL_REQUEST_FUND_EVENT_TOPIC: {
        "event": "InitiateWithdraw",
    },
    settings.RETHINK_DELTA_NEUTRAL_COMPLETE_WITHDRAW_EVENT_TOPIC: {
        "event": "Withdrawn",
    },
}


def _extract_rethink_event(entry):
    """Extract data from Rethink vault events"""
    # Get the from_address from indexed parameter
    from_address = None
    if len(entry["topics"]) >= 2:
        from_address = f'0x{entry["topics"][1].hex()[26:]}'

    # Decode the data field based on event type
    data = entry["data"].hex()

    if entry["topics"][0].hex() == settings.RETHINK_DELTA_NEUTRAL_DEPOSIT_EVENT_TOPIC:
        # UserDeposited event: amount
        amount = int(data[2:66], 16) / 1e18  # WETH has 18 decimals
        return amount, 0, from_address

    elif entry["topics"][0].hex() in [
        settings.RETHINK_DELTA_NEUTRAL_REQUEST_FUND_EVENT_TOPIC,
        settings.RETHINK_DELTA_NEUTRAL_COMPLETE_WITHDRAW_EVENT_TOPIC,
    ]:
        # InitiateWithdrawal and Withdrawn events: amount and shares
        amount = int(data[2:66], 16) / 1e18
        shares = int(data[66:130], 16) / 1e18
        return amount, shares, from_address

    elif (
        entry["topics"][0].hex()
        == settings.RETHINK_DELTA_NEUTRAL_DEPOSITED_TO_FUND_CONTRACT_EVENT_TOPIC
    ):
        # DepositedToFundContract event: amount only
        return 0, 0, None


def update_tvl(session: Session, vault: Vault, weth_amount: float):
    if vault.tvl is None:
        vault.tvl = 0.0

    vault.tvl += weth_amount
    logger.info(
        f"TVL updated for vault {vault.name}: {vault.tvl} USD (WETH amount: {weth_amount})"
    )
    session.add(vault)
    session.commit()


def handle_deposit_event(
    session: Session,
    user_portfolio: UserPortfolio | None,
    value: float,
    from_address: str,
    vault: Vault,
    shares: float,
    *args,
    **kwargs,
):
    """Handle user deposit event"""
    current_pps = get_current_pps(kwargs.get("vault_contract"), decimals=1e18)
    weth_price = get_price(f"{vault.underlying_asset}USDT")
    usd_value = value * weth_price

    if user_portfolio is None:
        logger.info(f"User deposit {from_address} amount = {usd_value} USD")
        user_portfolio = UserPortfolio(
            vault_id=vault.id,
            user_address=from_address,
            total_balance=value,
            init_deposit=value,
            pending_deposit=value,
            entry_price=current_pps,
            pnl=0,
            status=PositionStatus.ACTIVE,
            trade_start_date=datetime.now(timezone.utc),
            total_shares=shares,
        )
        session.add(user_portfolio)
    else:
        logger.info(f"User position before update {user_portfolio}")
        user_portfolio.total_balance += value
        user_portfolio.init_deposit += value
        user_portfolio.pending_deposit += value
        user_portfolio.total_shares += shares
        session.add(user_portfolio)

    session.commit()
    update_tvl(session, vault, value)
    return user_portfolio


def handle_deposited_to_fund_contract(
    session: Session,
    vault: Vault,
    vault_contract: Contract,
    value: float,
):
    """Handle system deposit to fund contract event"""
    # Get all active portfolios for this vault
    portfolios = session.exec(
        select(UserPortfolio)
        .where(UserPortfolio.vault_id == vault.id)
        .where(UserPortfolio.status == PositionStatus.ACTIVE)
    ).all()

    for portfolio in portfolios:
        # Get user's current shares from contract
        shares = (
            vault_contract.functions.balanceOf(
                Web3.to_checksum_address(portfolio.user_address)
            ).call()
            / 1e18
        )

        # Update portfolio shares
        portfolio.total_shares = shares
        portfolio.pending_deposit = 0
        session.add(portfolio)

    session.commit()
    logger.info(
        f"Updated shares for {len(portfolios)} portfolios after fund contract deposit"
    )


def process_event(session: Session, msg: dict, event_filters: dict) -> None:
    """Process a single event message and handle it appropriately"""
    try:
        res = msg["result"]
        if res["topics"][0].hex() not in event_filters:
            return

        # Get event type
        event_filter = event_filters[res["topics"][0].hex()]

        # Get vault contract for additional operations
        vault = session.exec(
            select(Vault).where(Vault.contract_address == res["address"])
        ).first()

        if not vault:
            logger.warning(f"Vault not found for address {res['address']}")
            return

        vault_contract, _ = get_vault_contract(vault, abi_name="rethink_yield_v2")

        # Extract event data
        value, shares, from_address = _extract_rethink_event(res)

        # Get user portfolio if applicable
        user_portfolio = None
        if from_address:
            user_portfolio = session.exec(
                select(UserPortfolio)
                .where(UserPortfolio.user_address == from_address)
                .where(UserPortfolio.vault_id == vault.id)
                .where(UserPortfolio.status == PositionStatus.ACTIVE)
            ).first()

        # Handle event based on type
        if event_filter["event"] == "Deposit":
            handle_deposit_event(
                session,
                user_portfolio,
                value,
                from_address,
                vault,
                shares,
                vault_contract=vault_contract,
            )
        elif event_filter["event"] == "DepositedToFundContract":
            handle_deposited_to_fund_contract(session, vault, vault_contract, value)
        elif event_filter["event"] == "InitiateWithdraw":
            handle_initiate_withdraw_event(
                session,
                user_portfolio,
                value,
                from_address,
                shares,
                get_current_pps(vault_contract),
            )
        elif event_filter["event"] == "Withdrawn":
            handle_withdrawn_event(session, user_portfolio, value, from_address, vault)

    except Exception as e:
        logger.error(f"Error processing event: {e}")
        logger.error(traceback.format_exc())


class RethinkWeb3Listener(Web3Listener):
    def __init__(self, connection_url):
        super().__init__(connection_url)

    async def listen_for_events(self, network: NetworkChain):
        while True:
            try:
                with Session(engine) as session:
                    # Query active Rethink vaults
                    vaults = session.exec(
                        select(Vault)
                        .where(Vault.category == VaultCategory.real_yield_v2)
                        .where(Vault.is_active == True)
                        .where(Vault.network_chain == network)
                    ).all()
                    logger.info("Subscribing to %d Rethink vaults...", len(vaults))

                for vault in vaults:
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
                    with Session(engine) as session:
                        process_event(session, msg, RETHINK_EVENT_FILTERS)

            except (ConnectionClosedError, ConnectionClosedOK) as e:
                self.logger.error("Websocket connection closed", exc_info=True)
                await asyncio.sleep(2)
                await self.reconnect()
            except Exception as e:
                logger.error(f"Error: {e}")
                logger.error(traceback.format_exc())


@click.command()
@click.option("--network", default="arbitrum_one", help="Blockchain network to use")
def main(network: str):
    setup_logging_to_console()
    setup_logging_to_file(
        app=f"rethink_web3_listener_{network}", level=logging.INFO, logger=logger
    )

    # Parse network to NetworkChain enum
    network_chain = NetworkChain[network.lower()]

    # Select connection URL based on network
    if network_chain == NetworkChain.arbitrum_one:
        connection_url = settings.ARBITRUM_MAINNET_INFURA_WEBSOCKER_URL
    elif network_chain == NetworkChain.ethereum:
        connection_url = settings.ETHER_MAINNET_INFURA_WEBSOCKER_URL
    elif network_chain == NetworkChain.base:
        connection_url = settings.BASE_MAINNET_WSS_NETWORK_RPC
    else:
        raise ValueError(f"Unsupported network: {network}")

    web3_listener = RethinkWeb3Listener(connection_url)
    asyncio.run(web3_listener.run(network_chain))


def test():
    from web3.datastructures import AttributeDict

    msg = {
        "subscription": "0x97950178d62d5c3dfc163cb84d30aed2",
        "result": AttributeDict(
            {
                "address": "0x1D47CA37872f4c19Cf6931f801E99A0d618E3688",
                "topics": [
                    HexBytes(
                        "0xda43df27a339f80303355a0fac6c644bb25b52dc0317394b127e505099ff55ca"
                    )
                ],
                "data": HexBytes("0x"),
                "blockNumber": 283341942,
                "transactionHash": HexBytes(
                    "0xbb45f92ca77717fc3364bd040b01c5d96884c32c4294ba0c36d3e9021ffce53a"
                ),
                "transactionIndex": 7,
                "blockHash": HexBytes(
                    "0x26ba68ae7ef4e6694242aa09f8fd788295bbfb2169f8186e3aa30eb10aa3cc5c"
                ),
                "logIndex": 18,
                "removed": False,
            }
        ),
    }
    with Session(engine) as session:
        process_event(session, msg, RETHINK_EVENT_FILTERS)


if __name__ == "__main__":
    main()
    # test()
