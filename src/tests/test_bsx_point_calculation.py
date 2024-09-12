import json
import uuid
import pytest
from unittest.mock import call, patch, MagicMock
from uuid import UUID, uuid4
from sqlmodel import Session, select
from bg_tasks.bsx_point_calculation import distribute_points_to_users
from core import constants
from models.point_distribution_history import PointDistributionHistory
from models.user_points import UserPointAudit, UserPoints
from models.user_portfolio import UserPortfolio
from models.vaults import Vault
from core.db import engine


db_session = Session(engine)
VAULT_ID = uuid.UUID("be740e89-c676-4d16-bead-133fcc844e96")


@pytest.fixture(autouse=True)
def remove_data():
    db_session.query(PointDistributionHistory).delete()
    db_session.query(UserPortfolio).delete()
    db_session.query(UserPointAudit).delete()
    db_session.query(UserPoints).delete()
    db_session.query(Vault).delete()

    db_session.commit()


def create_or_get_vault() -> Vault:
    vault = db_session.exec(select(Vault).where(Vault.id == VAULT_ID)).first()
    if vault:
        return vault

    vault = Vault(
        contract_address="0x55c4c840F9Ac2e62eFa3f12BaBa1B57A1208B6F5",
        category="real_yield",
        strategy_name=constants.PENDLE_HEDGING_STRATEGY,
        network_chain="arbitrum_one",
        name="Pendle",
        id=VAULT_ID,
    )
    db_session.add(vault)
    db_session.commit()

    return vault


def test_distribute_points():
    vault = create_or_get_vault()

    partner_name = "partner1"
    total_earned_points = 120

    portfolio_user1 = UserPortfolio(
        user_address="user1_address",
        init_deposit=100,
        vault_id=vault.id,
        total_balance=75,
        total_shares=0,
    )
    portfolio_user2 = UserPortfolio(
        user_address="user2_address",
        init_deposit=50,
        vault_id=vault.id,
        total_balance=50,
        total_shares=10,
    )

    db_session.add_all([portfolio_user1, portfolio_user2])
    db_session.commit()

    # Distribute points
    distribute_points_to_users(
        vault.id, [portfolio_user1, portfolio_user2], total_earned_points, partner_name
    )

    # Verify points were distributed correctly
    points_user1 = db_session.exec(
        select(UserPoints).where(
            UserPoints.wallet_address == portfolio_user1.user_address
        )
    ).first()

    points_user2 = db_session.exec(
        select(UserPoints).where(
            UserPoints.wallet_address == portfolio_user2.user_address
        )
    ).first()

    assert (
        points_user1.points == 80
    ), f"Expected 80 points for user1, got {points_user1.points}"
    assert (
        points_user2.points == 40
    ), f"Expected 40 points for user2, got {points_user2.points}"
