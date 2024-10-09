"""add_index_OnchainTransactionHistory

Revision ID: 7e42c3186e9b
Revises: 1ac9b29f6c92
Create Date: 2024-10-09 09:20:03.306534

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "7e42c3186e9b"
down_revision: Union[str, None] = "1ac9b29f6c92"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_index(
        op.f("ix_onchain_transaction_history_method_id"),
        "onchain_transaction_history",
        ["method_id"],
        unique=False,
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(
        op.f("ix_onchain_transaction_history_method_id"),
        table_name="onchain_transaction_history",
    )
    # ### end Alembic commands ###