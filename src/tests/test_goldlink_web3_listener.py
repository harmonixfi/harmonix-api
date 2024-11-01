import os
import uuid
from unittest.mock import patch

import pytest
from hexbytes import HexBytes
from sqlmodel import Session

from core import constants
from core.db import engine
from models.point_distribution_history import PointDistributionHistory
from models.pps_history import PricePerShareHistory
from models.user_points import UserPointAudit, UserPoints
from models.user_portfolio import PositionStatus, UserPortfolio
from models.vault_performance import VaultPerformance
from models.vaults import Vault
from web3_listener import _extract_delta_neutral_event, handle_event

VAULT_ID = uuid.UUID("2f1eb35d-c482-42d1-b8c9-f796ed1e12a1")


@pytest.fixture(scope="module")
def db_session():
    session = Session(engine)
    yield session


# create fixture run before every test
@pytest.fixture(autouse=True)
def seed_data(db_session: Session):
    assert os.getenv("POSTGRES_DB") == "test"

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
        contract_address="0xa9BE190b8348F18466dC84cC2DE69C04673c5aca",
        category="rewards",
        strategy_name=constants.DELTA_NEUTRAL_STRATEGY,
        network_chain="arbitrum_one",
        name="Gold Link",
        slug=constants.GOLD_LINK_SLUG,
        id=VAULT_ID,
        is_active=True,
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
        "address": "0xa9BE190b8348F18466dC84cC2DE69C04673c5aca",
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


def test_extract_goldlink_event(event_data):

    # Call the method with the event data
    total_amount, shares, from_address = _extract_delta_neutral_event(event_data)

    # Assert the expected values (based on the mock data)
    assert total_amount == 20
    assert shares == 20
    assert from_address == "0x20f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7"


@patch("web3_listener.KyberSwapService.get_token_price")
def test_handle_event_goldlink_deposit(
    mock_get_token_price, event_data, db_session: Session
):
    mock_get_token_price.return_value = 4700.0  # Example value in USD

    vault_address = "0xa9BE190b8348F18466dC84cC2DE69C04673c5aca"

    amount = 20_000000
    shares = 20_00000
    event_data["data"] = HexBytes("0x{:064x}".format(amount) + "{:064x}".format(shares))
    handle_event(db_session, vault_address, event_data, "Deposit")

    user_portfolio = (
        db_session.query(UserPortfolio)
        .filter(
            UserPortfolio.user_address == "0x20f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7"
        )
        .first()
    )

    assert user_portfolio is not None
    assert round(user_portfolio.total_balance) == 20
    assert user_portfolio.status == PositionStatus.ACTIVE


@patch("web3_listener.KyberSwapService.get_token_price")
def test_handle_event_goldlink_initiate_withdraw(
    mock_get_token_price, event_data, db_session: Session
):
    mock_get_token_price.return_value = 4700.0  # Example value in USD

    vault_address = "0xa9BE190b8348F18466dC84cC2DE69C04673c5aca"

    amount = 200_000000
    shares = 200_000000
    event_data["data"] = HexBytes("0x{:064x}".format(amount) + "{:064x}".format(shares))

    # First handle the deposit
    handle_event(db_session, vault_address, event_data, "Deposit")

    # Now handle initiate withdrawal

    handle_event(db_session, vault_address, event_data, "InitiateWithdraw")

    user_portfolio = (
        db_session.query(UserPortfolio)
        .filter(
            UserPortfolio.user_address == "0x20f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7"
        )
        .first()
    )

    assert user_portfolio is not None
    assert user_portfolio.pending_withdrawal == 200  # shares in the withdrawal
    assert user_portfolio.status == PositionStatus.ACTIVE
    assert (
        user_portfolio.init_deposit == 0
    )  # Withdrawal reduces the initial deposit amount
