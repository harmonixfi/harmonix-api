import uuid
import sqlmodel


class VaultRewards(sqlmodel.SQLModel, table=True):
    __tablename__ = "vault_rewards"

    id: uuid.UUID = sqlmodel.Field(default_factory=uuid.uuid4, primary_key=True)
    vault_id: uuid.UUID
    earned_rewards: float | None = None
    unclaimed_rewards: float | None = None
    claimed_rewards: float | None = None
    token_address: str | None = None
    token_name: str | None = None
