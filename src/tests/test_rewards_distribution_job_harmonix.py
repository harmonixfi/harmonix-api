from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch
from uuid import UUID
import pytest
from core import constants
from models.user import User
from models.user_portfolio import UserPortfolio, PositionStatus
from models.user_rewards import UserRewards
from models.vaults import Vault
from models.reward_distribution_config import RewardDistributionConfig
from bg_tasks.rewards_distribution_job_harmonix import (
    calculate_reward_distributions,
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


@pytest.fixture
def hype_vault():
    return Vault(
        id=UUID("12345678-1234-5678-1234-567812345678"),
        name="$HYPE delta neutral",
        slug=constants.HYPE_DELTA_NEUTRA_SLUG,
        vault_currency="USDC",
        is_active=True,
    )


@pytest.fixture
def users():
    return [
        User(
            wallet_address="0x1111111111111111111111111111111111111111",
            created_at=datetime.now(timezone.utc),
        ),
        User(
            wallet_address="0x2222222222222222222222222222222222222222",
            created_at=datetime.now(timezone.utc),
        ),
    ]


@pytest.fixture
def user_portfolios(hype_vault, users):
    return [
        UserPortfolio(
            vault_id=hype_vault.id,
            user_address=users[0].wallet_address,
            total_balance=1000.0,
            init_deposit=1000.0,
            status=PositionStatus.ACTIVE,
            trade_start_date=datetime.now(timezone.utc),
        ),
        UserPortfolio(
            vault_id=hype_vault.id,
            user_address=users[1].wallet_address,
            total_balance=500.0,
            init_deposit=500.0,
            status=PositionStatus.ACTIVE,
            trade_start_date=datetime.now(timezone.utc),
        ),
    ]


@pytest.fixture
def reward_config(hype_vault):
    current_date = datetime.now(timezone.utc)
    return RewardDistributionConfig(
        vault_id=hype_vault.id,
        reward_token="$HYPE",
        total_reward=100.0,
        week=1,
        distribution_percentage=0.35,
        start_date=current_date - timedelta(days=7),
        created_at=current_date - timedelta(days=7),
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


@patch("bg_tasks.rewards_distribution_job_harmonix.session")
def test_calculate_reward_distributions(mock_session, hype_vault, users, user_portfolios, reward_config):
    """Test reward distribution calculation for the HYPE vault.
    
    Test Scenario:
    -------------
    - Vault: $HYPE delta neutral vault
    - Time: End of Week 1
    - Total Reward Pool: 100 HYPE tokens
    - Week 1 Distribution: 35% of total pool (35 HYPE tokens)
    
    User Deposits:
    -------------
    - User 1: 1000 USDC (66.67% of total deposits)
    - User 2: 500 USDC (33.33% of total deposits)
    - Total Deposits: 1500 USDC
    
    Expected Rewards Distribution:
    ---------------------------
    - User 1: 23.33 HYPE tokens (66.67% of 35 HYPE)
    - User 2: 11.67 HYPE tokens (33.33% of 35 HYPE)
    
    Test Flow:
    ---------
    1. Mocks database session to simulate:
       - Reward config for Week 1 (35% distribution)
       - Two active user positions
       - No existing reward records (new users)
    
    2. Executes calculate_reward_distributions()
    
    3. Verifies:
       - Correct number of database calls (6 total)
       - Creation of new UserRewards records for both users
       - Creation of UserRewardAudit records for tracking changes
       - Accurate reward amounts based on deposit proportions
    """
    # Arrange
    mock_reward_config = Mock()
    mock_reward_config.first.return_value = reward_config
    
    mock_user_positions = Mock()
    mock_user_positions.all.return_value = user_portfolios
    
    mock_user = Mock()
    mock_user.first.side_effect = users
    
    # Create mock user rewards (initially None for new users)
    mock_user_rewards = Mock()
    mock_user_rewards.first.return_value = None
    
    mock_session.exec.side_effect = [
        mock_reward_config,  # for get_reward_distribution_config
        mock_user_positions, # for get_active_user_positions
        mock_user,          # for get_user_by_wallet (user 1)
        mock_user_rewards,  # for get_user_reward (user 1)
        mock_user,          # for get_user_by_wallet (user 2)
        mock_user_rewards,  # for get_user_reward (user 2)
    ]

    # Expected calculations
    total_reward = reward_config.total_reward * reward_config.distribution_percentage  # 100 * 0.35 = 35
    total_deposits = sum(p.init_deposit for p in user_portfolios)  # 1500
    expected_user1_reward = (1000 / total_deposits) * total_reward  # 23.33...
    expected_user2_reward = (500 / total_deposits) * total_reward   # 11.66...

    # Act
    calculate_reward_distributions(hype_vault)

    # Assert
    assert mock_session.exec.call_count == 6  # Verify all expected DB queries were made
    
    # Get all add() calls to session
    add_calls = [
        call for call in mock_session.mock_calls 
        if "add" in str(call)
    ]
    
    # Should have 2 UserRewards adds (one per user) and 2 UserRewardAudit adds
    assert len(add_calls) == 4
    
    # Verify the UserRewards records that were added
    user_rewards_adds = [
        call for call in add_calls 
        if "UserRewards" in str(call.args[0].__class__.__name__)
    ]
    assert len(user_rewards_adds) == 2
    
    # Verify reward amounts are correct (with floating point tolerance)
    rewards = [call.args[0].total_reward for call in user_rewards_adds]
    assert any(abs(r - expected_user1_reward) < 0.0001 for r in rewards)
    assert any(abs(r - expected_user2_reward) < 0.0001 for r in rewards)


@patch("bg_tasks.rewards_distribution_job_harmonix.session")
def test_calculate_reward_distributions_week_2(mock_session, hype_vault, users, user_portfolios, reward_config):
    """Test reward distribution calculation for the HYPE vault for week 2.
    
    Test Scenario:
    -------------
    - Vault: $HYPE delta neutral vault
    - Time: End of Week 2
    - Total Reward Pool: 100 HYPE tokens
    - Week 2 Distribution: 30% of total pool (30 HYPE tokens)
    
    User Deposits:
    -------------
    - User 1: 1000 USDC (66.67% of total deposits)
    - User 2: 500 USDC (33.33% of total deposits)
    - Total Deposits: 1500 USDC
    
    Expected Rewards Distribution:
    ---------------------------
    - User 1: 20 HYPE tokens (66.67% of 30 HYPE)
    - User 2: 10 HYPE tokens (33.33% of 30 HYPE)
    
    Test Flow:
    ---------
    1. Mocks database session to simulate:
       - Reward config for Week 2 (30% distribution)
       - Two active user positions
       - Existing reward records from Week 1 for both users
    
    2. Executes calculate_reward_distributions()
    
    3. Verifies:
       - Correct number of database calls (6 total)
       - Update of existing UserRewards records for both users
       - Creation of UserRewardAudit records for tracking changes
       - Accurate reward amounts based on deposit proportions
    """
    # Arrange
    # Mock the reward configuration for week 2
    week_2_reward_config = RewardDistributionConfig(
        vault_id=hype_vault.id,
        reward_token="$HYPE",
        total_reward=100.0,
        week=2,
        distribution_percentage=0.30,
        start_date=datetime.now(timezone.utc) - timedelta(days=7),  # Assume it's the end of week 2
        created_at=datetime.now(timezone.utc) - timedelta(days=7),
    )

    mock_reward_config = Mock()
    mock_reward_config.first.return_value = week_2_reward_config
    
    mock_user_positions = Mock()
    mock_user_positions.all.return_value = user_portfolios
    
    mock_user = Mock()
    mock_user.first.side_effect = users
    
    # Create mock user rewards for week 1
    mock_user_rewards = Mock()
    mock_user_rewards.first.side_effect = [
        UserRewards(vault_id=hype_vault.id, wallet_address=users[0].wallet_address, total_reward=23.33, updated_at=datetime.now(timezone.utc) - timedelta(days=1)),  # User 1
        UserRewards(vault_id=hype_vault.id, wallet_address=users[1].wallet_address, total_reward=11.67, updated_at=datetime.now(timezone.utc) - timedelta(days=1)),  # User 2
    ]
    
    mock_session.exec.side_effect = [
        mock_reward_config,  # for get_reward_distribution_config
        mock_user_positions, # for get_active_user_positions
        mock_user,          # for get_user_by_wallet (user 1)
        mock_user_rewards,  # for get_user_reward (user 1)
        mock_user,          # for get_user_by_wallet (user 2)
        mock_user_rewards,  # for get_user_reward (user 2)
    ]

    # Expected calculations for week 2
    total_reward_week_2 = week_2_reward_config.total_reward * week_2_reward_config.distribution_percentage  # 100 * 0.30 = 30
    total_deposits = sum(p.init_deposit for p in user_portfolios)  # 1500
    expected_user1_reward_week_2 = (1000 / total_deposits) * total_reward_week_2  # 20 HYPE
    expected_user2_reward_week_2 = (500 / total_deposits) * total_reward_week_2   # 10 HYPE

    # Act
    calculate_reward_distributions(hype_vault)

    # Assert
    assert mock_session.exec.call_count == 6  # Verify all expected DB queries were made
    
    # Get all add() calls to session
    add_calls = [
        call for call in mock_session.mock_calls 
        if "add" in str(call)
    ]
    
    # Should have 2 UserRewards updates and 2 UserRewardAudit adds
    assert len(add_calls) == 4
    
    # Verify the UserRewards records that were updated
    user_rewards_adds = [
        call for call in add_calls 
        if "UserRewards" in str(call.args[0].__class__.__name__)
    ]
    assert len(user_rewards_adds) == 2
    
    # Verify reward amounts are correct (with floating point tolerance)
    rewards = [call.args[0].total_reward for call in user_rewards_adds]
    assert any(abs(r - expected_user1_reward_week_2) < 0.0001 for r in rewards)
    assert any(abs(r - expected_user2_reward_week_2) < 0.0001 for r in rewards)
