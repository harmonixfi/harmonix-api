import uuid
from unittest.mock import patch

import pytest
from hexbytes import HexBytes
from sqlalchemy.orm import Session

from core import constants
from core.db import engine
from models.point_distribution_history import PointDistributionHistory
from models.pps_history import PricePerShareHistory
from models.user_points import UserPointAudit, UserPoints
from models.user_portfolio import PositionStatus, UserPortfolio
from models.vault_performance import VaultPerformance
from models.vaults import Vault
from web3_listener import handle_event


@pytest.fixture(scope="module")
def db_session():
    session = Session(engine)
    yield session


# create fixture run before every test
@pytest.fixture(autouse=True)
def seed_data(db_session: Session):
    db_session.query(UserPointAudit).delete()
    db_session.query(UserPoints).delete()
    db_session.query(PointDistributionHistory).delete()
    db_session.query(VaultPerformance).delete()
    db_session.query(UserPortfolio).delete()
    db_session.commit()
    db_session.query(PricePerShareHistory).delete()
    db_session.commit()
    db_session.query(Vault).delete()
    db_session.commit()

    vault = Vault(
        contract_address="0x55c4c840F9Ac2e62eFa3f12BaBa1B57A1208B6F5",
        category="real_yield",
        strategy_name=constants.PENDLE_HEDGING_STRATEGY,
        network_chain="arbitrum_one",
        name="Pendle",
        id=uuid.uuid4(),
    )
    db_session.add(vault)
    db_session.commit()


@pytest.fixture
def event_data():
    return {
        "removed": False,
        "logIndex": 1,
        "transactionIndex": 0,
        "transactionHash": "0xcf7fd3f78a02f233cd7bbb64aec516997aad6212cf86d0599d7db5021aa38f6c",
        "blockHash": "0x4874e743d6e778c5b4af1c0547f7bf5f8d6bcfae8541022d9b1959ce7d41da9f",
        "blockNumber": 192713205,
        "address": "0x55c4c840F9Ac2e62eFa3f12BaBa1B57A1208B6F5",
        "data": HexBytes(
            "0x0000000000000000000000000000000000000000000000000000000001312d000000000000000000000000000000000000000000000000000000000001312d00"
        ),
        "topics": [
            HexBytes(
                "0x73a19dd210f1a7f902193214c0ee91dd35ee5b4d920cba8d519eca65a7b488ca"
            ),
            HexBytes(
                "0x00000000000000000000000020f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7"
            ),
        ],
    }


@patch("web3_listener._extract_pendle_event")
@patch("web3_listener.KyberSwapService.get_token_price")
def test_handle_event_pendle_deposit(
    mock_get_token_price, mock_extract_event, event_data, db_session: Session
):
    mock_get_token_price.return_value = 4700.0  # Example value in USD
    mock_extract_event.return_value = (
        470_000000000000000000,
        3076,
        600,
        "0x20f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7",
    )  # pt_amount, sc_amount, shares, from_address

    vault_address = "0x55c4c840F9Ac2e62eFa3f12BaBa1B57A1208B6F5"
    vault = (
        db_session.query(Vault).filter(Vault.contract_address == vault_address).first()
    )

    event_data["data"] = HexBytes(
        "0x{:064x}".format(470_000000000000000000)
        + "{:064x}".format(3076)
        + "{:064x}".format(600)
    )
    handle_event(vault_address, event_data, "Deposit")

    user_portfolio = (
        db_session.query(UserPortfolio)
        .filter(
            UserPortfolio.user_address == "0x20f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7"
        )
        .first()
    )

    assert user_portfolio is not None
    assert round(user_portfolio.total_balance) == round(
        4700 + 3076
    )  # pt_in_usd + sc_amount
    assert user_portfolio.status == PositionStatus.ACTIVE


@patch("web3_listener._extract_pendle_event")
@patch("web3_listener.KyberSwapService.get_token_price")
def test_handle_event_pendle_initiate_withdraw(
    mock_get_token_price, mock_extract_event, event_data, db_session: Session
):
    mock_get_token_price.return_value = 4700.0  # Example value in USD
    mock_extract_event.return_value = (
        470_000000000000000000,
        3076,
        600,
        "0x20f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7",
    )  # pt_amount, sc_amount, shares, from_address

    vault_address = "0x55c4c840F9Ac2e62eFa3f12BaBa1B57A1208B6F5"
    vault = (
        db_session.query(Vault).filter(Vault.contract_address == vault_address).first()
    )

    event_data["data"] = HexBytes(
        "0x{:064x}".format(470_000000000000000000)
        + "{:064x}".format(3076)
        + "{:064x}".format(600)
    )

    # First handle the deposit
    handle_event(vault_address, event_data, "Deposit")

    # Now handle initiate withdrawal
    handle_event(vault_address, event_data, "InitiateWithdraw")

    user_portfolio = (
        db_session.query(UserPortfolio)
        .filter(
            UserPortfolio.user_address == "0x20f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7"
        )
        .first()
    )

    assert user_portfolio is not None
    assert user_portfolio.pending_withdrawal == 600  # shares in the withdrawal
    assert user_portfolio.status == PositionStatus.ACTIVE
    assert (
        user_portfolio.init_deposit == 0
    )  # Withdrawal reduces the initial deposit amount


@pytest.fixture
def pendle_event_data():
    return {
        "removed": False,
        "logIndex": 1,
        "transactionIndex": 0,
        "transactionHash": "0xcf7fd3f78a02f233cd7bbb64aec516997aad6212cf86d0599d7db5021aa38f6c",
        "blockHash": "0x4874e743d6e778c5b4af1c0547f7bf5f8d6bcfae8541022d9b1959ce7d41da9f",
        "blockNumber": 192713205,
        "address": "0x55c4c840F9Ac2e62eFa3f12BaBa1B57A1208B6F5",
        "data": HexBytes(
            "0x00000000000000000000000000000000000000000000000000470de4df8200000000000000000000000000000000000000000000000000000000000003076dca00000000000000000000000000000000000000000000000000000000060ab383"
        ),
        "topics": [
            HexBytes(
                "0x73a19dd210f1a7f902193214c0ee91dd35ee5b4d920cba8d519eca65a7b488ca"
            ),
            HexBytes(
                "0x00000000000000000000000020f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7"
            ),
        ],
    }
