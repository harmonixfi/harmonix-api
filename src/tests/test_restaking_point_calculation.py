import os
from typing import List
from unittest import mock
from unittest.mock import patch
import uuid

import pytest
from sqlmodel import Session, select

from bg_tasks.restaking_point_calculation import (
    GET_POINTS_SERVICE,
    distribute_points,
    distribute_points_to_users,
    get_earned_points,
    main,
    get_previous_point_distribution,
    process_point_distribution,
)
from core import constants
from core.db import engine
from models import UserPoints, UserPortfolio, Vault, PointDistributionHistory
from models.user_points import UserPointAudit
from models.user_portfolio import PositionStatus
from models.vaults import VaultCategory
from schemas import EarnedRestakingPoints
from core.constants import RENZO, ZIRCUIT, KELPDAO, PARTNER_KELPDAOGAIN, EIGENLAYER

VAULT_ID = uuid.UUID("be740e89-c676-4d16-bead-133fcc844e96")


@pytest.fixture(scope="module")
def db_session():
    session = Session(engine)
    yield session


@pytest.fixture(autouse=True)
def clean_user_portfolio(db_session: Session):
    assert os.getenv("POSTGRES_DB") == "test"
    db_session.query(PointDistributionHistory).delete()
    db_session.query(UserPointAudit).delete()
    db_session.query(UserPoints).delete()
    db_session.query(UserPortfolio).delete()
    db_session.query(Vault).delete()
    db_session.commit()


@pytest.fixture(scope="function")
def mock_vault(db_session):
    vault = Vault(
        id=VAULT_ID,
        name="Test Vault",
        contract_address="0x1234567890abcdef",
        category=VaultCategory.points,
        is_active=True,
    )
    db_session.add(vault)
    db_session.commit()
    return vault


@pytest.fixture(scope="function")
def mock_user_position(db_session, mock_vault) -> List[UserPortfolio]:
    user_position = UserPortfolio(
        vault_id=mock_vault.id,
        user_address="0xABCDEF123456",
        init_deposit=1000.0,
        status=PositionStatus.ACTIVE,
        total_balance=75,
        total_shares=0,
    )
    db_session.add(user_position)
    db_session.commit()
    user_position2 = UserPortfolio(
        vault_id=mock_vault.id,
        user_address="user_address2",
        init_deposit=500.0,
        status=PositionStatus.ACTIVE,
        total_balance=40,
        total_shares=0,
    )
    db_session.add(user_position2)
    db_session.commit()

    return [user_position, user_position2]


def fake_earned_restaking_points(
    partner_name: str = constants.RENZO,
) -> EarnedRestakingPoints:
    expected_points = EarnedRestakingPoints(
        wallet_address="0xABCDEF123456",
        total_points=100,
        eigen_layer_points=50,
        partner_name=partner_name,
    )
    return expected_points


@pytest.fixture
def mock_services():
    """Fixture to set up mock services in GET_POINTS_SERVICE."""
    with patch.dict(
        GET_POINTS_SERVICE,
        {
            constants.RENZO: mock.Mock(
                return_value=fake_earned_restaking_points(constants.RENZO)
            ),
            constants.ZIRCUIT: mock.Mock(
                return_value=fake_earned_restaking_points(constants.ZIRCUIT)
            ),
            constants.KELPDAO: mock.Mock(
                return_value=fake_earned_restaking_points(constants.KELPDAO)
            ),
            constants.PARTNER_KELPDAOGAIN: mock.Mock(
                return_value=fake_earned_restaking_points(constants.PARTNER_KELPDAOGAIN)
            ),
        },
    ) as mock_services:
        yield mock_services


def test_get_earned_points_valid_partner(mock_services, mock_vault):
    """Test get_earned_points with a valid partner."""
    partner_name = constants.RENZO
    points = get_earned_points(mock_vault.contract_address, partner_name)
    assert points == fake_earned_restaking_points(partner_name)
    mock_services[partner_name].assert_called_once_with(mock_vault.contract_address)


def test_get_previous_point_distribution(db_session, mock_vault):
    history_entry = PointDistributionHistory(
        vault_id=mock_vault.id, partner_name=RENZO, point=100
    )
    db_session.add(history_entry)
    db_session.commit()

    result = get_previous_point_distribution(mock_vault.id, RENZO)
    assert result == 100


def test_distribute_points_to_users(db_session, mock_vault, mock_user_position):
    distribute_points_to_users(
        vault_id=mock_vault.id,
        user_positions=mock_user_position,
        earned_points=150,
        partner_name=RENZO,
    )

    user1_points = (
        db_session.query(UserPoints).filter_by(wallet_address="0xABCDEF123456").first()
    )
    assert user1_points.points == 100  # Adjust as per distribution logic

    user2_points = (
        db_session.query(UserPoints).filter_by(wallet_address="user_address2").first()
    )
    assert user2_points.points == 50


def test_process_point_distribution(db_session, mock_vault, mock_user_position):
    earned_points = fake_earned_restaking_points(PARTNER_KELPDAOGAIN)
    process_point_distribution(
        vault=mock_vault,
        partner_name=PARTNER_KELPDAOGAIN,
        user_positions=mock_user_position,
        total_earned_points=earned_points,
        earned_point_value=150,
    )

    user1_points = (
        db_session.query(UserPoints).filter_by(wallet_address="0xABCDEF123456").first()
    )
    assert user1_points.points == 100  # Adjust as per distribution logic

    user2_points = (
        db_session.query(UserPoints).filter_by(wallet_address="user_address2").first()
    )
    assert user2_points.points == 50
