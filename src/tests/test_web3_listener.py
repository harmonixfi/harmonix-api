from datetime import datetime, timedelta, timezone
import math
import os
from unittest.mock import Mock, patch
import uuid

from hexbytes import HexBytes
import pendulum
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import settings
from core.db import engine
from models.point_distribution_history import PointDistributionHistory
from models.pps_history import PricePerShareHistory
from models.user_points import UserPointAudit, UserPoints
from models.user_portfolio import PositionStatus, UserPortfolio
from models.vault_performance import VaultPerformance
from models.vaults import Vault
import schemas
from web3_listener import handle_event, handle_withdrawn_event


@pytest.fixture(scope="module")
def db_session():
    session = Session(engine)
    yield session


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
        contract_address="0x18994527E6FfE7e91F1873eCA53e900CE0D0f276",
        category="real_yield",
        strategy_name="options_wheel_strategy",
        network_chain="arbitrum_one",
        name="Options Wheel Strategy",
        id=uuid.uuid4(),
    )
    db_session.add(vault)

    vault = Vault(
        contract_address="0x55c4c840F9Ac2e62eFa3f12BaBa1B57A1208B6F5",
        category="real_yield",
        strategy_name="delta_neutral_strategy",
        network_chain="arbitrum_one",
        name="Delta Neutral Strategy",
        id=uuid.uuid4(),
    )
    db_session.add(vault)

    vault = Vault(
        contract_address="0x55c4c840F9Ac2e62eFa3f12BaBa1B57A1208B6F9",
        category="points",
        strategy_name="delta_neutral_strategy",
        network_chain="arbitrum_one",
        name="Renzo Delta Neutral Strategy",
        id=uuid.uuid4(),
    )
    db_session.add(vault)

    vault = Vault(
        contract_address="0x55c4c840F9Ac2e62eFa3f12BaBa1B57A1208B6G8",
        category="real_yield",
        strategy_name="",
        network_chain="arbitrum_one",
        name="Solv",
        slug="arbitrum-wbtc-vault",
        id=uuid.uuid4(),
    )
    db_session.add(vault)
    db_session.commit()


def test_handle_event_deposit(event_data, db_session: Session):
    amount = 20_000000
    shares = 20_000000

    vault_address = "0x18994527E6FfE7e91F1873eCA53e900CE0D0f276"
    vault = (
        db_session.query(Vault).filter(Vault.contract_address == vault_address).first()
    )

    event_data["data"] = HexBytes("0x{:064x}".format(amount) + "{:064x}".format(shares))
    handle_event(vault_address, event_data, "Deposit")
    user_portfolio = (
        db_session.query(UserPortfolio)
        .filter(
            UserPortfolio.user_address == "0x20f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7"
        )
        .first()
    )
    assert user_portfolio is not None
    assert user_portfolio.total_balance == 20

    # Get the latest pps from pps_history table
    latest_pps = (
        db_session.query(PricePerShareHistory.price_per_share)
        .filter(PricePerShareHistory.vault_id == vault.id)
        .order_by(PricePerShareHistory.datetime.desc())
        .first()
    )
    if latest_pps is not None:
        latest_pps = latest_pps[0]
    else:
        latest_pps = 1
    assert (
        round(user_portfolio.total_shares, 2)
        == math.ceil(user_portfolio.total_balance / latest_pps * 100) / 100
    )
    assert user_portfolio.entry_price == latest_pps


# @patch("web3_listener._extract_stablecoin_event")
def test_handle_event_deposit_calculating_entry_price(event_data, db_session: Session):
    db_session.query(UserPortfolio).filter(
        UserPortfolio.user_address == "0x20f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7"
    ).delete()
    db_session.commit()

    # mock_extract_event.return_value = (
    #     20,
    #     100,
    #     "0x20f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7",
    # )  # amount, from_address

    vault_address = "0x55c4c840F9Ac2e62eFa3f12BaBa1B57A1208B6F5"
    vault = (
        db_session.query(Vault).filter(Vault.contract_address == vault_address).first()
    )

    # Get the latest pps from pps_history table
    latest_pps: PricePerShareHistory = (
        db_session.query(PricePerShareHistory)
        .filter(PricePerShareHistory.vault_id == vault.id)
        .order_by(PricePerShareHistory.datetime.desc())
        .first()
    )
    if latest_pps is None:
        latest_pps = PricePerShareHistory(
            price_per_share=1,
            datetime=pendulum.now(tz=pendulum.UTC).add(days=-1),
            vault_id=vault.id,
            id=1,
        )

    amount = 20_000000
    shares = 20_000000
    event_data["data"] = HexBytes("0x{:064x}".format(amount) + "{:064x}".format(shares))
    handle_event(vault_address, event_data, "Deposit")
    user_portfolio = (
        db_session.query(UserPortfolio)
        .filter(
            UserPortfolio.user_address == "0x20f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7"
        )
        .first()
    )
    assert user_portfolio is not None
    assert user_portfolio.total_balance == 20

    assert round(user_portfolio.total_shares, 2) == round(
        user_portfolio.total_balance / latest_pps.price_per_share, 2
    )
    assert user_portfolio.entry_price == latest_pps.price_per_share

    # mock data for PricePerShareHistory by insert 1 row with price_per_share = latest_pps + 5%
    # with datetime = latest_pps.datetime + 1 day
    updated_pps = latest_pps.price_per_share * 1.05
    db_session.execute(
        PricePerShareHistory.__table__.insert(),
        {
            "vault_id": vault.id,
            "price_per_share": updated_pps,
            "datetime": latest_pps.datetime + timedelta(days=1),
        },
    )
    db_session.commit()

    amount = int(200 * 1e6)
    shares = int(200 / updated_pps * 1e6)
    event_data["data"] = HexBytes("0x{:064x}".format(amount) + "{:064x}".format(shares))
    handle_event(vault_address, event_data, "Deposit")

    user_portfolio = (
        db_session.query(UserPortfolio)
        .filter(
            UserPortfolio.user_address == "0x20f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7"
        )
        .first()
    )
    assert user_portfolio is not None
    assert user_portfolio.total_balance == 220

    expected_entry = (
        (20 / latest_pps.price_per_share) * latest_pps.price_per_share
        + (shares / 1e6) * updated_pps
    ) / ((20 / latest_pps.price_per_share) + (shares / 1e6))
    assert round(user_portfolio.entry_price, 2) == math.ceil(expected_entry * 100) / 100


@patch("web3_listener._extract_stablecoin_event")
def test_handle_event_deposit_then_init_withdraw(
    mock_extract_event, event_data, db_session: Session
):
    mock_extract_event.return_value = (
        200,
        100,
        "0x20f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7",
    )  # amount, from_address

    vault_address = "0x55c4c840F9Ac2e62eFa3f12BaBa1B57A1208B6F5"
    vault = (
        db_session.query(Vault).filter(Vault.contract_address == vault_address).first()
    )

    amount = 200_000000
    shares = 200_000000
    event_data["data"] = HexBytes("0x{:064x}".format(amount) + "{:064x}".format(shares))
    handle_event(vault_address, event_data, "Deposit")

    user_portfolio = (
        db_session.query(UserPortfolio)
        .filter(
            UserPortfolio.user_address == "0x20f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7"
        )
        .first()
    )
    assert user_portfolio is not None
    assert user_portfolio.total_balance == 200

    updated_pps = 1.05
    db_session.execute(
        PricePerShareHistory.__table__.insert(),
        {
            "vault_id": vault.id,
            "price_per_share": updated_pps,
            "datetime": datetime.now() + timedelta(days=1),
        },
    )
    db_session.commit()

    amount = int((200 * updated_pps) * 1e6)
    shares = int(200 * 1e6)
    event_data["data"] = HexBytes("0x{:064x}".format(amount) + "{:064x}".format(shares))
    handle_event(
        "0x55c4c840F9Ac2e62eFa3f12BaBa1B57A1208B6F5", event_data, "InitiateWithdraw"
    )
    db_session.commit()
    user_portfolio = (
        db_session.query(UserPortfolio)
        .filter(
            UserPortfolio.user_address == "0x20f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7"
        )
        .first()
    )
    assert user_portfolio is not None
    assert user_portfolio.pending_withdrawal == 200
    assert user_portfolio.init_deposit == 0

    amount = 200_000000
    shares = 200_000000
    event_data["data"] = HexBytes("0x{:064x}".format(amount) + "{:064x}".format(shares))
    handle_event("0x55c4c840F9Ac2e62eFa3f12BaBa1B57A1208B6F5", event_data, "Withdrawn")
    db_session.commit()
    user_portfolio = (
        db_session.query(UserPortfolio)
        .filter(
            UserPortfolio.user_address == "0x20f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7"
        )
        .first()
    )
    assert user_portfolio is not None
    assert user_portfolio.total_balance == 0
    assert user_portfolio.status == PositionStatus.CLOSED


def test_handle_solv_events(event_data, db_session: Session):
    db_session.query(UserPortfolio).filter(
        UserPortfolio.user_address == "0x20f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7"
    ).delete()
    db_session.commit()

    vault_address = "0x55c4c840F9Ac2e62eFa3f12BaBa1B57A1208B6G8"
    vault = (
        db_session.query(Vault).filter(Vault.contract_address == vault_address).first()
    )

    amount = 100000
    shares = 936810457735051
    event_data["data"] = HexBytes("0x{:064x}".format(amount) + "{:064x}".format(shares))
    handle_event(vault_address, event_data, "Deposit")
    user_portfolio = (
        db_session.query(UserPortfolio)
        .filter(
            UserPortfolio.user_address == "0x20f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7"
        )
        .first()
    )
    assert user_portfolio is not None
    assert user_portfolio.total_balance == 0.001

    amount = 200000
    shares = 1873009926952612
    event_data["data"] = HexBytes("0x{:064x}".format(amount) + "{:064x}".format(shares))
    handle_event(vault_address, event_data, "Deposit")
    db_session.refresh(user_portfolio)
    user_portfolio = (
        db_session.query(UserPortfolio)
        .filter(
            UserPortfolio.user_address == "0x20f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7"
        )
        .first()
    )
    assert user_portfolio is not None
    assert user_portfolio.total_balance == 0.003

    amount = 100000
    shares = 936810457735051
    event_data["data"] = HexBytes("0x{:064x}".format(amount) + "{:064x}".format(shares))
    handle_event(vault_address, event_data, "InitiateWithdraw")
    db_session.commit()
    user_portfolio = (
        db_session.query(UserPortfolio)
        .filter(
            UserPortfolio.user_address == "0x20f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7"
        )
        .first()
    )
    assert user_portfolio is not None
    assert user_portfolio.pending_withdrawal == 936810457735051 / 1e18
    assert user_portfolio.init_deposit == 0.002


@pytest.fixture
def mock_session():
    return Mock()


@pytest.fixture
def mock_user_portfolio():
    user_portfolio = Mock()
    user_portfolio.total_balance = 1000
    user_portfolio.pending_withdrawal = 500
    user_portfolio.initiated_withdrawal_at = datetime.now(timezone.utc)
    user_portfolio.status = PositionStatus.ACTIVE  # Assuming OPEN is a valid status
    return user_portfolio


@pytest.fixture
def mock_vault():
    vault = Mock()
    vault.name = "Test Vault"
    vault.tvl = 1000.0
    return vault


def test_handle_withdrawn_event_updates_tvl(
    mock_session, mock_user_portfolio, mock_vault
):
    value = 500
    from_address = "0x1234"

    with patch("web3_listener.logger") as mock_logger, patch(
        "web3_listener.update_tvl"
    ) as mock_update_tvl:

        # Call the function
        handle_withdrawn_event(
            session=mock_session,
            user_portfolio=mock_user_portfolio,
            value=value,
            from_address=from_address,
            vault=mock_vault,
        )

        # Verify that update_tvl was called with correct parameters
        mock_update_tvl.assert_called_once_with(mock_session, mock_vault, -500.0)

        # Check that user_portfolio attributes were updated correctly
        assert mock_user_portfolio.total_balance == 500
        assert mock_user_portfolio.pending_withdrawal == 0
        assert mock_user_portfolio.initiated_withdrawal_at is None

        # Verify that session.add was called with the updated user_portfolio
        mock_session.add.assert_called_once_with(mock_user_portfolio)

        # Verify logger info calls
        mock_logger.info.assert_any_call(
            f"User complete withdrawal {from_address} {value}"
        )
        mock_logger.info.assert_any_call(
            f"User with address {from_address} updated in user_portfolio table"
        )
