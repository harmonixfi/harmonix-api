import os
from typing import List
from unittest.mock import MagicMock, patch
import uuid

import pytest
from sqlmodel import Session, select

from bg_tasks.goldlink_arb_reward_calculation import (
    distribute_rewards,
    distribute_rewards_to_users,
    get_previous_reward_distribution,
    get_rewards,
    main,
)
from core import constants
from core.db import engine
from models.reward_distribution_history import RewardDistributionHistory
from models.user_portfolio import UserPortfolio
from models.user_rewards import UserRewardAudit, UserRewards
from models.vault_rewards import VaultRewards
from models.vaults import Vault
from schemas.earned_restaking_rewards import EarnedRestakingRewards

VAULT_ID = uuid.UUID("be740e89-c676-4d16-bead-133fcc844e96")


@pytest.fixture(scope="module")
def db_session():
    session = Session(engine)
    yield session


@pytest.fixture(autouse=True)
def clean_user_portfolio(db_session: Session):
    assert os.getenv("POSTGRES_DB") == "test"
    db_session.query(RewardDistributionHistory).delete()
    db_session.query(UserRewardAudit).delete()
    db_session.query(UserRewards).delete()
    db_session.query(UserPortfolio).delete()
    db_session.query(Vault).delete()
    db_session.commit()

    # Insert test data into Vaults table
    vault = Vault(
        name="GoldLink",
        contract_address="0x55c4c840f9ac2e62efa3f12bba1b57a12086f5",
        routes='["goldlink"]',
        category="rewards",
        network_chain="arbitrum_one",
        is_active=True,
        strategy_name=constants.DELTA_NEUTRAL_STRATEGY,
        id=VAULT_ID,
    )
    db_session.add(vault)

    # Insert test data into UserPortfolio table
    user_portfolio = UserPortfolio(
        vault_id=VAULT_ID,
        user_address="0xBC05da14287317FE12B1a2b5a0E1d756Ff1801Aa",
        total_balance=1000,
        init_deposit=1000,
        total_shares=1000,
    )
    db_session.add(user_portfolio)

    db_session.commit()

    vault_reward = VaultRewards(
        vault_id=VAULT_ID,
        earned_rewards=10,
        claimed_rewards=10,
        unclaimed_rewards=0,
        wallet_address="0x123",
    )
    db_session.add(vault_reward)

    db_session.commit()


def test_get_rewards(db_session: Session):
    # Arrange
    vault = db_session.exec(select(Vault).where(Vault.id == VAULT_ID)).first()
    # Act
    rewards = get_rewards(vault)

    # Assert
    assert rewards.wallet_address == "0x55c4c840f9ac2e62efa3f12bba1b57a12086f5"
    assert rewards.total_rewards > 0
    assert rewards.partner_name == constants.DELTA_NEUTRAL_STRATEGY


def test_distribute_rewards_to_users(db_session):
    # Arrange
    user_positions = db_session.exec(
        select(UserPortfolio).where(UserPortfolio.vault_id == VAULT_ID)
    ).all()
    # Act
    distribute_rewards_to_users(
        vault_id=VAULT_ID,
        user_positions=user_positions,
        earned_rewards=1000,
        partner_name=constants.DELTA_NEUTRAL_STRATEGY,
    )

    # Assert
    user_rewards = (
        db_session.query(UserRewards)
        .filter_by(wallet_address=user_positions[0].user_address)
        .first()
    )
    assert user_rewards.total_reward == 1000
    assert user_rewards.partner_name == constants.DELTA_NEUTRAL_STRATEGY


def test_distribute_rewards(db_session):
    # Arrange
    vault = db_session.exec(select(Vault).where(Vault.id == VAULT_ID)).first()
    total_earned_rewards = EarnedRestakingRewards(
        wallet_address=vault.contract_address,
        total_rewards=500,
        partner_name=constants.DELTA_NEUTRAL_STRATEGY,
    )
    user_positions = db_session.exec(
        select(UserPortfolio).where(UserPortfolio.vault_id == VAULT_ID)
    ).all()
    # Act
    distribute_rewards(vault, "goldlink", user_positions, 500, total_earned_rewards)

    # Assert
    reward_history = db_session.exec(
        select(RewardDistributionHistory).where(
            RewardDistributionHistory.vault_id == VAULT_ID
        )
    ).first()

    assert reward_history is not None
    assert reward_history.total_reward == 500
