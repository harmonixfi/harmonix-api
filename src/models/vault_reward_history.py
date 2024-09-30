import uuid
import sqlmodel
from datetime import datetime as dt, timezone


class VaultRewardHistory(sqlmodel.SQLModel):
    __tablename__ = "vault_reward_history"

    id: uuid.UUID = sqlmodel.Field(default_factory=uuid.uuid4, primary_key=True)
    vault_id: uuid.UUID
    earned_rewards: float | None = None
    unclaimed_rewards: float | None = None
    claimed_rewards: float | None = None
    datetime: dt = sqlmodel.Field(default=dt.now(timezone.utc), index=True)
