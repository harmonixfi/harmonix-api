from datetime import datetime, timezone
import math
from unittest.mock import Mock, patch

from hexbytes import HexBytes
import pytest
from sqlmodel import Session, select

from core.db import engine
from models.point_distribution_history import PointDistributionHistory
from models.pps_history import PricePerShareHistory
from models.user_points import UserPointAudit, UserPoints
from models.user_portfolio import PositionStatus, UserPortfolio
from models.vault_performance import VaultPerformance
from models.vaults import NetworkChain, Vault, VaultMetadata
from rethink_web3_listener import (
    handle_deposit_event,
    handle_deposited_to_fund_contract,
    process_event,
    _extract_rethink_event,
)
from core.config import settings

# Initialize test fixtures
@pytest.fixture(scope="module")
def db_session():
    session = Session(engine)
    yield session

@pytest.fixture
def mock_vault_contract():
    contract = Mock()
    contract.functions.balanceOf.return_value = 10 * 10**18  # 10 shares
    contract.functions.pricePerShare.return_value = 1 * 10**18  # 1.0 PPS
    return contract

@pytest.fixture
def event_data():
    return {
        "removed": False,
        "logIndex": 1,
        "transactionIndex": 0,
        "transactionHash": HexBytes("0xcf7fd3f78a02f233cd7bbb64aec516997aad6212cf86d0599d7db5021aa38f6c"),
        "blockHash": HexBytes("0x4874e743d6e778c5b4af1c0547f7bf5f8d6bcfae8541022d9b1959ce7d41da9f"),
        "blockNumber": 192713205,
        "address": "0x55c4c840F9Ac2e62eFa3f12BaBa1B57A1208B6F5",
        "data": HexBytes("0x" + "0" * 64 + "0" * 64),  # Will be updated in tests
        "topics": [
            HexBytes("0x0000000000000000000000000000000000000000000000000000000000000000"),  # Will be updated
            HexBytes("0x00000000000000000000000020f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7"),
        ],
    }

@pytest.fixture(autouse=True)
def seed_data(db_session: Session):
    # Clear existing data
    db_session.query(UserPointAudit).delete()
    db_session.query(UserPoints).delete()
    db_session.query(PointDistributionHistory).delete()
    db_session.query(VaultPerformance).delete()
    db_session.query(UserPortfolio).delete()
    db_session.query(VaultMetadata).delete()
    db_session.commit()
    db_session.query(PricePerShareHistory).delete()
    db_session.commit()
    db_session.query(Vault).delete()
    db_session.commit()

    # Create test vault
    vault = Vault(
        contract_address="0x55c4c840F9Ac2e62eFa3f12BaBa1B57A1208B6F5",
        category="real_yield",
        strategy_name="Rethink",
        network_chain=NetworkChain.arbitrum_one,
        name="Test Rethink Vault",
    )
    db_session.add(vault)
    db_session.commit()

@pytest.fixture
def mock_get_price():
    with patch("rethink_web3_listener.get_price") as mock:
        mock.return_value = 2000  # Mock WETH price as $2000
        yield mock

@pytest.fixture
def mock_get_current_pps():
    with patch("rethink_web3_listener.get_current_pps") as mock:
        mock.return_value = 1.0  # Mock PPS as 1.0
        yield mock

def test_user_deposit_new_portfolio(db_session, event_data, mock_get_price, mock_get_current_pps):
    """Test user deposit when no existing portfolio exists"""
    # Setup
    vault = db_session.exec(select(Vault)).first()
    from_address = "0x20f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7"

    # Execute
    portfolio = handle_deposit_event(
        session=db_session,
        user_portfolio=None,
        value=10,  # 10 WETH
        from_address=from_address,
        vault=vault,
        shares=10,  # 10 shares
        vault_contract=None  # Not needed since we're mocking get_current_pps
    )

    # Verify
    assert portfolio is not None
    assert portfolio.total_balance == 20000  # 10 WETH * $2000
    assert portfolio.total_shares == 10
    assert portfolio.status == PositionStatus.ACTIVE
    assert portfolio.entry_price == 1.0

def test_user_deposit_existing_portfolio(db_session, event_data, mock_get_price, mock_get_current_pps):
    """Test user deposit when portfolio already exists"""
    # Setup
    vault = db_session.exec(select(Vault)).first()
    from_address = "0x20f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7"
    
    # Create existing portfolio
    existing_portfolio = UserPortfolio(
        vault_id=vault.id,
        user_address=from_address,
        total_balance=10000,  # $10000
        init_deposit=10000,
        total_shares=5,
        entry_price=1.0,
        status=PositionStatus.ACTIVE,
        trade_start_date=datetime.now(timezone.utc),
    )
    db_session.add(existing_portfolio)
    db_session.commit()

    # Execute
    updated_portfolio = handle_deposit_event(
        session=db_session,
        user_portfolio=existing_portfolio,
        value=5,  # 5 WETH
        from_address=from_address,
        vault=vault,
        shares=5,  # 5 shares
        vault_contract=None  # Not needed since we're mocking get_current_pps
    )

    # Verify
    assert updated_portfolio.total_balance == 20000  # Previous $10000 + (5 WETH * $2000)
    assert updated_portfolio.total_shares == 10  # Previous 5 + 5 new shares
    assert updated_portfolio.status == PositionStatus.ACTIVE

def test_handle_deposited_to_fund_contract(db_session):
    """Test system deposit to fund contract updates user shares correctly"""
    # Setup
    vault = db_session.exec(select(Vault)).first()
    user1 = "0x20f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7"
    user2 = "0x30f89ba1b0fc1e83f9aef0a134095cd63f7e8cc8"

    # Create test portfolios
    portfolios = [
        UserPortfolio(
            vault_id=vault.id,
            user_address=addr,
            total_balance=10000,
            init_deposit=10000,
            total_shares=5,
            entry_price=1.0,
            status=PositionStatus.ACTIVE,
            trade_start_date=datetime.now(timezone.utc),
        )
        for addr in [user1, user2]
    ]
    for p in portfolios:
        db_session.add(p)
    db_session.commit()

    # Mock the vault contract's balanceOf function chain
    mock_contract = Mock()
    mock_balance_of = Mock()
    mock_balance_of.call = Mock(return_value=10 * 10**18)  # 10 shares
    mock_contract.functions.balanceOf = Mock(return_value=mock_balance_of)

    # Execute
    handle_deposited_to_fund_contract(
        session=db_session,
        vault=vault,
        vault_contract=mock_contract,
        value=20,  # 20 WETH
    )

    # Verify
    for addr in [user1, user2]:
        portfolio = db_session.exec(
            select(UserPortfolio)
            .where(UserPortfolio.user_address == addr)
        ).first()
        assert portfolio.total_shares == 10  # Updated from contract.balanceOf

def test_extract_rethink_event_deposit(event_data):
    """Test extraction of deposit event data"""
    # Setup deposit event data
    amount = 10 * 10**18  # 10 WETH
    event_data["data"] = HexBytes("0x" + hex(amount)[2:].zfill(64))
    event_data["topics"][0] = HexBytes(settings.RETHINK_DELTA_NEUTRAL_DEPOSIT_EVENT_TOPIC)

    # Execute
    amount, shares, from_address = _extract_rethink_event(event_data)

    # Verify
    assert amount == 10  # 10 WETH
    assert shares == 0
    assert from_address == "0x20f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7"

def test_extract_rethink_event_initiate_withdraw(event_data):
    """Test extraction of initiate withdraw event data"""
    # Setup initiate withdraw event data
    amount = 5 * 10**18  # 5 WETH
    shares = 2 * 10**18  # 2 shares
    event_data["data"] = HexBytes("0x" + hex(amount)[2:].zfill(64) + hex(shares)[2:].zfill(64))
    event_data["topics"][0] = HexBytes(settings.RETHINK_DELTA_NEUTRAL_REQUEST_FUND_EVENT_TOPIC)

    # Execute
    amount, shares, from_address = _extract_rethink_event(event_data)

    # Verify
    assert amount == 5  # 5 WETH
    assert shares == 2  # 2 shares
    assert from_address == "0x20f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7"

def test_extract_rethink_event_withdrawn(event_data):
    """Test extraction of withdrawn event data"""
    # Setup withdrawn event data
    amount = 5 * 10**18  # 5 WETH
    shares = 2 * 10**18  # 2 shares
    event_data["data"] = HexBytes("0x" + hex(amount)[2:].zfill(64) + hex(shares)[2:].zfill(64))
    event_data["topics"][0] = HexBytes(settings.RETHINK_DELTA_NEUTRAL_COMPLETE_WITHDRAW_EVENT_TOPIC)

    # Execute
    amount, shares, from_address = _extract_rethink_event(event_data)

    # Verify
    assert amount == 5  # 5 WETH
    assert shares == 2  # 2 shares
    assert from_address == "0x20f89ba1b0fc1e83f9aef0a134095cd63f7e8cc7"

def test_extract_rethink_event_deposited_to_fund_contract(event_data):
    """Test extraction of deposited to fund contract event data"""
    # Setup deposited to fund contract event data
    amount = 10 * 10**18  # 10 WETH
    event_data["data"] = HexBytes("0x" + hex(amount)[2:].zfill(64))
    event_data["topics"][0] = HexBytes(settings.RETHINK_DELTA_NEUTRAL_DEPOSITED_TO_FUND_CONTRACT_EVENT_TOPIC)

    # Execute
    amount, shares, from_address = _extract_rethink_event(event_data)

    # Verify
    assert amount == 10  # 10 WETH
    assert shares == 0  # No shares for this event
    assert from_address is None  # No from_address for this event