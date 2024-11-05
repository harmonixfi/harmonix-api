from datetime import datetime, timezone
import uuid
from sqlmodel import Session, select

from core import constants
from models.reward_distribution_history import RewardDistributionHistory
from models.vault_rewards import VaultRewards


class VaultRewardsService:
    def __init__(self, session: Session):
        self.session = session

    def get_vault_earned_reward_by_partner(
        self, vault_id: uuid.UUID
    ) -> RewardDistributionHistory:
        statement = (
            select(RewardDistributionHistory)
            .where(RewardDistributionHistory.vault_id == vault_id)
            .order_by(RewardDistributionHistory.created_at.desc())
        )

        reward_dist_hist = self.session.exec(statement).first()
        if reward_dist_hist is None:
            return RewardDistributionHistory(
                vault_id=vault_id,
                partner_name=constants.PARTNER_GODLINK,
                total_reward=0.0,
                created_at=datetime.now(timezone.utc),
            )
        return reward_dist_hist

    def get_rewards_earned(self, vault_id: uuid.UUID) -> float:
        vault_reward = self.session.exec(
            select(VaultRewards).where(VaultRewards.vault_id == vault_id)
        ).first()

        return vault_reward.earned_rewards if vault_reward else float(0.0)
