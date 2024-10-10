"""Update network chain

Revision ID: 12f73b279f08
Revises: 051f0339f486
Create Date: 2024-10-10 14:08:07.065650

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '12f73b279f08'
down_revision: Union[str, None] = '051f0339f486'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE networkchain ADD VALUE 'sepolia'")


def downgrade() -> None:
    pass
