from uuid import uuid4
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone

from bg_tasks.points_distribution_job_harmonix import (
    harmonix_distribute_points,
    update_referral_points,
)
from models.referral_points import ReferralPoints
from models.referrals import Referral
from models.user_points_history import UserPointsHistory


@pytest.fixture
def mock_session():
    return MagicMock()


@pytest.fixture
def mock_logger():
    with patch("bg_tasks.points_distribution_job_harmonix.logger") as logger:
        yield logger


@pytest.fixture
def mock_adjust_referral_points():
    with patch(
        "bg_tasks.points_distribution_job_harmonix.adjust_referral_points_within_bounds"
    ) as adjust_mock:
        adjust_mock.return_value = 50  # Adjusted points for tests
        yield adjust_mock


@pytest.fixture
def mock_uuid():
    with patch("uuid.uuid4") as uuid_mock:
        uuid_mock.return_value = "test-uuid"
        yield uuid_mock


@patch("bg_tasks.points_distribution_job_harmonix.logger")
def test_no_active_reward_session(mock_logger):
    mock_session = MagicMock()
    with patch("bg_tasks.points_distribution_job_harmonix.session", mock_session):
        mock_session.exec.return_value.first.return_value = None

        harmonix_distribute_points(datetime.now(tz=timezone.utc))

        mock_logger.info.assert_called_with(
            "No active reward session found for Harmonix."
        )


@patch("bg_tasks.points_distribution_job_harmonix.logger")
def test_no_reward_session_config(mock_logger):
    mock_session = MagicMock()
    mock_exec_result = MagicMock()  # Mock the result of session.exec

    with patch("bg_tasks.points_distribution_job_harmonix.session", mock_session):
        # Configure the first call to exec to return a valid mock reward session
        mock_exec_result.first.side_effect = [
            MagicMock(),  # Mock reward session
            None,  # No reward session config
        ]
        mock_session.exec.return_value = mock_exec_result

        harmonix_distribute_points(datetime.now(tz=timezone.utc))

        mock_logger.info.assert_called_once_with(
            "No reward session config found for Harmonix."
        )


@patch("bg_tasks.points_distribution_job_harmonix.logger")
def test_reward_session_not_started(mock_logger):
    session_mock = MagicMock()
    current_time = datetime.now(tz=timezone.utc)
    start_date = current_time + timedelta(days=1)

    reward_session_mock = MagicMock(
        session_id="test_session", start_date=start_date, session_name="Test Session"
    )
    reward_session_config_mock = MagicMock(duration_in_minutes=60)

    with patch("bg_tasks.points_distribution_job_harmonix.session", session_mock):
        session_mock.exec.return_value.first.side_effect = [
            reward_session_mock,
            reward_session_config_mock,
        ]

        harmonix_distribute_points(current_time=current_time)

        mock_logger.info.assert_called_with("Test Session has not started yet.")


@patch("bg_tasks.points_distribution_job_harmonix.logger")
def test_maximum_points_distributed(logger_mock):
    session_mock = MagicMock()
    current_time = datetime.now(tz=timezone.utc)
    start_date = current_time - timedelta(days=1)

    reward_session_mock = MagicMock(
        session_id="test_session",
        start_date=start_date,
        session_name="Test Session",
        points_distributed=1000,
    )
    reward_session_config_mock = MagicMock()
    reward_session_config_mock.max_points = 1000
    reward_session_config_mock.duration_in_minutes = 1440  # Explicitly set the value

    with patch("bg_tasks.points_distribution_job_harmonix.session", session_mock):
        session_mock.exec.return_value.first.side_effect = [
            reward_session_mock,
            reward_session_config_mock,
        ]

        harmonix_distribute_points(current_time=current_time)

        logger_mock.info.assert_called_with(
            "Maximum points for Test Session have been distributed."
        )
