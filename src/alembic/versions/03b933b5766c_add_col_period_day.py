"""add_col_period_day

Revision ID: 03b933b5766c
Revises: 126a0e3cb181
Create Date: 2025-01-14 23:50:39.988814

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = "03b933b5766c"
down_revision: Union[str, None] = "126a0e3cb181"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "vault_apy_breakdown", sa.Column("period", sa.Integer(), nullable=True)
    )
    op.add_column(
        "vault_apy_component", sa.Column("period", sa.Integer(), nullable=True)
    )
    op.add_column(
        "vault_performance", sa.Column("reward_15d_apy", sa.Float(), nullable=True)
    )
    op.add_column(
        "vault_performance", sa.Column("reward_45d_apy", sa.Float(), nullable=True)
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("vault_performance", "reward_45d_apy")
    op.drop_column("vault_performance", "reward_15d_apy")
    op.drop_column("vault_apy_component", "period")
    op.drop_column("vault_apy_breakdown", "period")
    # ### end Alembic commands ###
