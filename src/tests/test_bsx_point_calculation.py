import json
import pytest
from unittest.mock import call, patch, MagicMock
from uuid import UUID

from bg_tasks.bsx_point_calculation import (
    calculate_point_distributions,
    distribute_points,
    distribute_points_to_users,
    get_previous_point_distribution,
)
from models.user_points import UserPoints

# Sample UUID for testing
vault_id = UUID("12345678-1234-5678-1234-567812345678")


@pytest.fixture
def mock_session():
    with patch("bg_tasks.bsx_point_calculation.session") as mock_session:
        yield mock_session


@pytest.fixture
def mock_logger():
    with patch("bg_tasks.bsx_point_calculation.logger") as mock_logger:
        yield mock_logger


@pytest.fixture
def mock_bsx_service():
    with patch("services.bsx_service") as mock_bsx_service:
        yield mock_bsx_service


def test_get_previous_point_distribution(mock_session):
    mock_point_dist = MagicMock(point=10)
    mock_session.exec.return_value.first.return_value = mock_point_dist

    result = get_previous_point_distribution(vault_id, "partner1")
    assert result == 10

    # Test case where no previous distribution exists
    mock_session.exec.return_value.first.return_value = None
    result = get_previous_point_distribution(vault_id, "partner1")
    assert result == 0


def test_distribute_points_to_users(mock_session, mock_logger):
    mock_vault_id = UUID("12345678-1234-5678-1234-567812345678")
    mock_partner_name = "partner1"
    mock_earned_points = 100
    mock_user_positions = [
        MagicMock(user_address="user1", init_deposit=50),
        MagicMock(user_address="user2", init_deposit=50),
    ]

    # Mock user points for the users
    mock_user_points = MagicMock(points=0)
    mock_session.exec.return_value.first.side_effect = [None, None]

    distribute_points_to_users(
        mock_vault_id, mock_user_positions, mock_earned_points, mock_partner_name
    )

    # Verify that session.add was called twice for both users
    assert (
        mock_session.add.call_count == 4
    )  # Two for UserPoints and two for UserPointAudit
    mock_session.commit.assert_called()


def test_distribute_points(mock_session, mock_logger):
    mock_vault = MagicMock(
        id=UUID("12345678-1234-5678-1234-567812345678"), routes='["partner1"]'
    )
    mock_partner_name = "partner1"
    mock_user_positions = [
        MagicMock(user_address="user1", init_deposit=50),
        MagicMock(user_address="user2", init_deposit=50),
    ]
    mock_earned_points_in_period = 100
    mock_total_earned_points = MagicMock(total_points=100)

    distribute_points(
        mock_vault,
        mock_partner_name,
        mock_user_positions,
        mock_earned_points_in_period,
        mock_total_earned_points,
    )

    # Verify that the correct session methods were called
    assert (
        mock_session.add.call_count == 5
    )  # Two for UserPoints, one for PointDistributionHistory
    mock_session.commit.assert_called()


def test_calculate_point_distributions(mock_session, mock_logger, mock_bsx_service):
    mock_vault = MagicMock(
        id=UUID("12345678-1234-5678-1234-567812345678"),
        routes='["partner1"]',
        name="Vault1",
    )
    mock_user_positions = [
        MagicMock(user_address="user1", init_deposit=50),
        MagicMock(user_address="user2", init_deposit=50),
    ]

    # Mock session exec for user positions and previous point distribution
    mock_session.exec.return_value.all.return_value = mock_user_positions
    mock_session.exec.return_value.first.return_value = MagicMock(point=50)

    # Mock earned points from bsx_service
    mock_bsx_service.get_points_earned.return_value = 200

    calculate_point_distributions(mock_vault)

    # Verify that the correct functions were called
    mock_session.exec.assert_called()
    mock_logger.info.assert_called()
    mock_session.commit.assert_called()
