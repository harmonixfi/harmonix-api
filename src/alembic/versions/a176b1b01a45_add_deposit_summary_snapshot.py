"""add_deposit_summary_snapshot

Revision ID: a176b1b01a45
Revises: 467a8686c4a3
Create Date: 2024-12-06 23:37:58.098851

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = "a176b1b01a45"
down_revision: Union[str, None] = "467a8686c4a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.execute("CREATE SCHEMA IF NOT EXISTS reports")
    op.create_table(
        "deposit_summary_snapshot",
        sa.Column("id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("datetime", sa.DateTime(), nullable=False),
        sa.Column("deposit_7_day", sa.Float(), nullable=False),
        sa.Column("deposit_30_day", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="reports",
    )
    op.create_index(
        op.f("ix_reports_deposit_summary_snapshot_datetime"),
        "deposit_summary_snapshot",
        ["datetime"],
        unique=False,
        schema="reports",
    )

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(
        op.f("ix_reports_deposit_summary_snapshot_datetime"),
        table_name="deposit_summary_snapshot",
        schema="reports",
    )
    op.drop_table("deposit_summary_snapshot", schema="reports")
    # ### end Alembic commands ###