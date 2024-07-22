"""update onchain_transaction_history table

Revision ID: 6375e63f1755
Revises: 906f1607795a
Create Date: 2024-07-21 11:50:17.243438

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "6375e63f1755"
down_revision: Union[str, None] = "906f1607795a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###

    op.add_column(
        "onchain_transaction_history",
        sa.Column("chain", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.add_column(
        "user_holding_asset_history",
        sa.Column("chain", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.drop_index(
        "ix_onchain_transaction_history_tx_hash",
        table_name="onchain_transaction_history",
    )
    op.create_index(
        op.f("ix_onchain_transaction_history_tx_hash"),
        "onchain_transaction_history",
        ["tx_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_onchain_transaction_history_chain"),
        "onchain_transaction_history",
        ["chain"],
        unique=False,
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(
        op.f("ix_onchain_transaction_history_chain"),
        table_name="onchain_transaction_history",
    )
    op.drop_index(
        op.f("ix_onchain_transaction_history_tx_hash"),
        table_name="onchain_transaction_history",
    )
    op.create_index(
        "ix_onchain_transaction_history_tx_hash",
        "onchain_transaction_history",
        ["tx_hash"],
        unique=False,
    )
    op.drop_column("onchain_transaction_history", "chain")
    op.drop_column("user_holding_asset_history", "chain")
    # ### end Alembic commands ###