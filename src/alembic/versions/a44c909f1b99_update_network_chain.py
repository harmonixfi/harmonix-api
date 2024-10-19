"""update_network_chain

Revision ID: a44c909f1b99
Revises: 1f8cf8642e91
Create Date: 2024-10-12 11:02:55.178609

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a44c909f1b99"
down_revision: Union[str, None] = "1f8cf8642e91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE networkchain ADD VALUE 'sepolia'")


def downgrade() -> None:
    pass
