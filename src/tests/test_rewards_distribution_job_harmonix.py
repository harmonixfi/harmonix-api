from datetime import datetime, timezone, timedelta
import os
from unittest.mock import Mock, patch
from uuid import UUID
import uuid
import pytest
from sqlmodel import Session
from core import constants
from models.user import User
from models.user_portfolio import UserPortfolio, PositionStatus
from models.user_rewards import UserRewardAudit, UserRewards
from models.vaults import Vault
from models.reward_distribution_config import RewardDistributionConfig
from bg_tasks.rewards_distribution_job_harmonix import (
    calculate_reward_distributions,
    get_user_reward,
    get_reward_distribution_config,
    get_active_user_positions,
    process_user_reward,
)
from core.db import engine

VAULT_ID = uuid.UUID("2f1eb35d-c482-42d1-b8c9-f796ed1e12a1")
CURRENT_DATE = datetime.now(timezone.utc)


def get_date_for_week(week: int = 1):
    return CURRENT_DATE + timedelta(days=7 * (week - 1))


def get_user_total_reward(db_session, wallet_address):
    """
    Retrieve the total reward for a user based on their wallet address.

    Args:
        db_session: The database session to use for the query.
        wallet_address (str): The wallet address of the user.

    Returns:
        float: The total reward of the user, or None if not found.
    """
    result = (
        db_session.query(UserRewards.total_reward)
        .where(UserRewards.wallet_address == wallet_address)
        .first()
    )
    return result[0] if result else 0


def calculate_expected_rewards(total_reward, user_portfolios):
    # Calculate the total deposits from all user portfolios
    total_deposits = sum(p.init_deposit for p in user_portfolios)
    # Calculate expected rewards for each user based on their deposit proportion
    return [(p.init_deposit / total_deposits) * total_reward for p in user_portfolios]


def execute_for_week(hype_vault: Vault, week: int = 1):
    date_of_week = get_date_for_week(week=week)
    calculate_reward_distributions(hype_vault, date_of_week)


def get_user_reward_data(db_session, user_portfolio):
    # Retrieve user reward data from the database
    return {
        "wallet_address": user_portfolio.user_address,
        "total_reward": get_user_total_reward(db_session, user_portfolio.user_address),
    }


@pytest.fixture(scope="module")
def db_session():
    session = Session(engine)
    yield session


# create fixture run before every test
@pytest.fixture(autouse=True)
def seed_data(db_session: Session, reward_configs, users, user_portfolios, hype_vault):
    assert os.getenv("POSTGRES_DB") == "test"

    db_session.query(UserPortfolio).delete()
    db_session.query(RewardDistributionConfig).delete()
    db_session.query(UserRewardAudit).delete()
    db_session.query(UserRewards).delete()
    db_session.query(Vault).delete()
    db_session.query(User).delete()
    db_session.commit()

    db_session.add(hype_vault)
    db_session.commit()
    db_session.add_all(users)
    db_session.commit()
    db_session.add_all(user_portfolios)
    db_session.commit()

    db_session.add_all(reward_configs)
    db_session.commit()


@pytest.fixture
def reward_configs():
    return [
        RewardDistributionConfig(
            vault_id=VAULT_ID,  # Sử dụng ID từ hype_vault
            reward_token="$HYPE",
            total_reward=100.0,
            week=1,
            distribution_percentage=0.35,
            start_date=get_date_for_week(week=1)
            - timedelta(days=1),  # Week 1 starts on the current date
            created_at=get_date_for_week(week=1) - timedelta(days=1),
        ),
        RewardDistributionConfig(
            vault_id=VAULT_ID,
            reward_token="$HYPE",
            total_reward=100.0,
            week=2,
            distribution_percentage=0.3,
            start_date=get_date_for_week(week=2)
            - timedelta(days=1),  # Week 2 starts 7 days after week 1
            created_at=get_date_for_week(week=2) - timedelta(days=1),
        ),
        RewardDistributionConfig(
            vault_id=VAULT_ID,
            reward_token="$HYPE",
            total_reward=100.0,
            week=3,
            distribution_percentage=0.25,
            start_date=get_date_for_week(week=3)
            - timedelta(days=1),  # Week 3 starts 14 days after week 1
            created_at=get_date_for_week(week=3) - timedelta(days=1),
        ),
        RewardDistributionConfig(
            vault_id=VAULT_ID,
            reward_token="$HYPE",
            total_reward=100.0,
            week=4,
            distribution_percentage=0.10,
            start_date=get_date_for_week(week=4)
            - timedelta(days=1),  # Week 4 starts 21 days after week 1
            created_at=get_date_for_week(week=4) - timedelta(days=1),
        ),
    ]


@pytest.fixture
def hype_vault():
    return Vault(
        contract_address="0xa9BE190b8348F18466dC84cC2DE69C04673c5aca",
        category="rewards",
        strategy_name=constants.DELTA_NEUTRAL_STRATEGY,
        network_chain="arbitrum_one",
        name="HYPE test",
        slug=constants.HYPE_DELTA_NEUTRA_SLUG,
        id=VAULT_ID,
        is_active=True,
    )


@pytest.fixture
def user_1():
    return User(
        wallet_address="0x1111111111111111111111111111111111111111",
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def user_2():
    return User(
        wallet_address="0x2222222222222222222222222222222222222222",
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def users(user_1, user_2):
    return [
        user_1,
        user_2,
    ]


@pytest.fixture
def user_portfolio_1(user_1):
    return UserPortfolio(
        vault_id=VAULT_ID,
        user_address=user_1.wallet_address,
        total_balance=1000.0,
        init_deposit=1000.0,
        status=PositionStatus.ACTIVE,
        trade_start_date=datetime.now(timezone.utc),
    )


@pytest.fixture
def user_portfolio_2(user_2):
    return UserPortfolio(
        vault_id=VAULT_ID,
        user_address=user_2.wallet_address,
        total_balance=500.0,
        init_deposit=500.0,
        status=PositionStatus.ACTIVE,
        trade_start_date=datetime.now(timezone.utc),
    )


@pytest.fixture
def user_portfolios(user_portfolio_1, user_portfolio_2):
    return [
        user_portfolio_1,
        user_portfolio_2,
    ]


def test_calculate_reward_distributions_week1(
    hype_vault, user_portfolio_1, user_portfolio_2, db_session: Session
):
    """Test reward distribution calculation for the HYPE vault for week 1.

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

    # Expected calculations
    total_reward_week_1 = 35  # 100 * 0.35 = 35
    expected_rewards_week_1 = calculate_expected_rewards(
        total_reward_week_1,
        [user_portfolio_1, user_portfolio_2],  # 23.33... and 11.67...
    )

    # Act
    date_of_week_1 = get_date_for_week(week=1)
    calculate_reward_distributions(hype_vault, date_of_week_1)

    # Assert
    user1_reward_week_1_data = get_user_reward_data(db_session, user_portfolio_1)
    user2_reward_week_1_data = get_user_reward_data(db_session, user_portfolio_2)

    # Verify reward amounts are correct (with floating point tolerance)
    assert (
        user1_reward_week_1_data["total_reward"] == expected_rewards_week_1[0]
    ), "User 1's total reward for week 1 is incorrect."

    assert (
        user2_reward_week_1_data["total_reward"] == expected_rewards_week_1[1]
    ), "User 2's total reward for week 1 is incorrect."


def test_calculate_reward_distributions_week_2(
    hype_vault, user_portfolio_1, user_portfolio_2, db_session: Session
):
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

    # Expected calculations for week 2
    total_reward_week_2 = 30  # 100 * 0.30 = 30, total reward for week 2
    expected_rewards_week_2 = calculate_expected_rewards(
        total_reward_week_2, [user_portfolio_1, user_portfolio_2]
    )

    # Generate data for week 1 to simulate existing reward records
    execute_for_week(hype_vault, week=1)

    # Get reward data for both users for week 1
    user1_reward_week_1_data = get_user_reward_data(db_session, user_portfolio_1)
    user2_reward_week_1_data = get_user_reward_data(db_session, user_portfolio_2)

    # Act: Calculate rewards for week 2
    date_of_week_2 = get_date_for_week(week=2)  # Get the date for the end of week 2
    calculate_reward_distributions(hype_vault, date_of_week_2)

    # Refresh all instances in the session to reflect the latest database state
    db_session.expire_all()

    # Get updated reward data for both users for week 2
    user1_reward_week_2_data = get_user_reward_data(db_session, user_portfolio_1)
    user2_reward_week_2_data = get_user_reward_data(db_session, user_portfolio_2)

    # Verify reward amounts are correct (with floating point tolerance)
    assert (
        user1_reward_week_1_data["total_reward"] + expected_rewards_week_2[0]
        == user1_reward_week_2_data["total_reward"]
    ), "User 1's total reward for week 2 is incorrect."

    assert (
        user2_reward_week_1_data["total_reward"] + expected_rewards_week_2[1]
        == user2_reward_week_2_data["total_reward"]
    ), "User 2's total reward for week 2 is incorrect."


def test_calculate_reward_distributions_week_3(
    hype_vault, user_portfolio_1, user_portfolio_2, db_session: Session
):
    """Test reward distribution calculation for the HYPE vault for week 3.

    Test Scenario:
    -------------
    - Vault: $HYPE delta neutral vault
    - Time: End of Week 3
    - Total Reward Pool: 100 HYPE tokens
    - Week 3 Distribution: 25% of total pool (25 HYPE tokens)

    User Deposits:
    -------------
    - User 1: 1000 USDC (66.67% of total deposits)
    - User 2: 500 USDC (33.33% of total deposits)
    - Total Deposits: 1500 USDC

    Expected Rewards Distribution:
    ---------------------------
    - User 1: 16.67 HYPE tokens (66.67% of 25 HYPE)
    - User 2: 8.33 HYPE tokens (33.33% of 25 HYPE)
    """
    # Expected calculations for week 3
    total_reward_week_3 = 25  # 100 * 0.25 = 25, total reward for week 3
    expected_rewards_week_3 = calculate_expected_rewards(
        total_reward_week_3, [user_portfolio_1, user_portfolio_2]
    )

    # Generate data for week 1 and 2 to simulate existing reward records
    execute_for_week(hype_vault, week=1)
    execute_for_week(hype_vault, week=2)

    # Get reward data for both users after week 2
    user1_reward_week_2_data = get_user_reward_data(db_session, user_portfolio_1)
    user2_reward_week_2_data = get_user_reward_data(db_session, user_portfolio_2)

    # Act: Calculate rewards for week 3
    date_of_week_3 = get_date_for_week(week=3)
    calculate_reward_distributions(hype_vault, date_of_week_3)

    # Refresh all instances in the session
    db_session.expire_all()

    # Get updated reward data for both users for week 3
    user1_reward_week_3_data = get_user_reward_data(db_session, user_portfolio_1)
    user2_reward_week_3_data = get_user_reward_data(db_session, user_portfolio_2)

    # Verify reward amounts are correct (with floating point tolerance)
    assert (
        user1_reward_week_2_data["total_reward"] + expected_rewards_week_3[0]
        == user1_reward_week_3_data["total_reward"]
    ), "User 1's total reward for week 3 is incorrect."

    assert (
        user2_reward_week_2_data["total_reward"] + expected_rewards_week_3[1]
        == user2_reward_week_3_data["total_reward"]
    ), "User 2's total reward for week 3 is incorrect."


def test_calculate_reward_distributions_week_4(
    hype_vault, user_portfolio_1, user_portfolio_2, db_session: Session
):
    """Test reward distribution calculation for the HYPE vault for week 4.

    Test Scenario:
    -------------
    - Vault: $HYPE delta neutral vault
    - Time: End of Week 4
    - Total Reward Pool: 100 HYPE tokens
    - Week 4 Distribution: 10% of total pool (10 HYPE tokens)

    User Deposits:
    -------------
    - User 1: 1000 USDC (66.67% of total deposits)
    - User 2: 500 USDC (33.33% of total deposits)
    - Total Deposits: 1500 USDC

    Expected Rewards Distribution:
    ---------------------------
    - User 1: 6.67 HYPE tokens (66.67% of 10 HYPE)
    - User 2: 3.33 HYPE tokens (33.33% of 10 HYPE)
    """
    # Expected calculations for week 4
    total_reward_week_4 = 10  # 100 * 0.10 = 10, total reward for week 4
    expected_rewards_week_4 = calculate_expected_rewards(
        total_reward_week_4, [user_portfolio_1, user_portfolio_2]
    )

    # Generate data for weeks 1, 2, and 3 to simulate existing reward records
    execute_for_week(hype_vault, week=1)
    execute_for_week(hype_vault, week=2)
    execute_for_week(hype_vault, week=3)

    # Get reward data for both users after week 3
    user1_reward_week_3_data = get_user_reward_data(db_session, user_portfolio_1)
    user2_reward_week_3_data = get_user_reward_data(db_session, user_portfolio_2)

    # Act: Calculate rewards for week 4
    date_of_week_4 = get_date_for_week(week=4)
    calculate_reward_distributions(hype_vault, date_of_week_4)

    # Refresh all instances in the session
    db_session.expire_all()

    # Get updated reward data for both users for week 4
    user1_reward_week_4_data = get_user_reward_data(db_session, user_portfolio_1)
    user2_reward_week_4_data = get_user_reward_data(db_session, user_portfolio_2)

    # Verify reward amounts are correct (with floating point tolerance)
    assert (
        user1_reward_week_3_data["total_reward"] + expected_rewards_week_4[0]
        == user1_reward_week_4_data["total_reward"]
    ), "User 1's total reward for week 4 is incorrect."

    assert (
        user2_reward_week_3_data["total_reward"] + expected_rewards_week_4[1]
        == user2_reward_week_4_data["total_reward"]
    ), "User 2's total reward for week 4 is incorrect."
