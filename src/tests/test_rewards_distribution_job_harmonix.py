from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch
from uuid import UUID
import pytest
from models.user import User
from models.user_portfolio import UserPortfolio, PositionStatus
from models.user_rewards import UserRewards
from models.vaults import Vault
from models.reward_distribution_config import RewardDistributionConfig
from bg_tasks.rewards_distribution_job_harmonix import (
    get_user_reward,
    get_reward_distribution_config,
    get_active_user_positions,
    process_user_reward,
)


@pytest.fixture
def sample_vault():
    return Vault(
        id=UUID("12345678-1234-5678-1234-567812345678"),
        name="Test Vault",
        slug="test-vault",
        is_active=True,
    )


@pytest.fixture
def sample_user():
    return User(
        wallet_address="0x1234567890123456789012345678901234567890",
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_user_portfolio(sample_vault, sample_user):
    return UserPortfolio(
        vault_id=sample_vault.id,
        user_address=sample_user.wallet_address,
        total_balance=1000.0,
        init_deposit=1000.0,
        status=PositionStatus.ACTIVE,
        trade_start_date=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_reward_config(sample_vault):
    return RewardDistributionConfig(
        vault_id=sample_vault.id,
        total_reward=1000.0,
        distribution_percentage=0.1,
        start_date=datetime.now(timezone.utc) - timedelta(days=1),
    )


@patch("bg_tasks.rewards_distribution_job_harmonix.session")
def test_get_user_reward(mock_session, sample_vault, sample_user):
    # Arrange
    mock_user_reward = UserRewards(
        vault_id=sample_vault.id,
        wallet_address=sample_user.wallet_address,
        total_reward=100.0,
    )
    mock_exec_result = Mock()
    mock_exec_result.first.return_value = mock_user_reward
    mock_session.exec.return_value = mock_exec_result

    # Act
    result = get_user_reward(sample_vault.id, sample_user.wallet_address)

    # Assert
    assert result == mock_user_reward
    assert result.total_reward == 100.0


@patch("bg_tasks.rewards_distribution_job_harmonix.session")
def test_get_reward_distribution_config(
    mock_session, sample_vault, sample_reward_config
):
    # Arrange
    mock_exec_result = Mock()
    mock_exec_result.first.return_value = sample_reward_config
    mock_session.exec.return_value = mock_exec_result

    # Act
    result = get_reward_distribution_config(datetime.now(timezone.utc), sample_vault.id)

    # Assert
    assert result == sample_reward_config
    assert result.total_reward == 1000.0
    assert result.distribution_percentage == 0.1


@patch("bg_tasks.rewards_distribution_job_harmonix.session")
def test_get_active_user_positions(mock_session, sample_user_portfolio):
    # Arrange
    mock_exec_result = Mock()
    mock_exec_result.all.return_value = [sample_user_portfolio]
    mock_session.exec.return_value = mock_exec_result

    # Act
    result = get_active_user_positions(sample_user_portfolio.vault_id)

    # Assert
    assert len(result) == 1
    assert result[0].total_balance == 1000.0
    assert result[0].status == PositionStatus.ACTIVE


@patch("bg_tasks.rewards_distribution_job_harmonix.session")
def test_process_user_reward_existing_user(mock_session, sample_vault, sample_user):
    # Arrange
    current_date = datetime.now(timezone.utc)
    existing_reward = UserRewards(
        vault_id=sample_vault.id,
        wallet_address=sample_user.wallet_address,
        total_reward=50.0,
        updated_at=current_date - timedelta(days=2),
    )

    mock_exec_result = Mock()
    mock_exec_result.first.return_value = existing_reward
    mock_session.exec.return_value = mock_exec_result

    # Act
    process_user_reward(
        sample_user,
        sample_vault.id,
        current_date - timedelta(days=1),
        50.0,
        current_date,
    )

    # Assert
    assert existing_reward.total_reward == 100.0
