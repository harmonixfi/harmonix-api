"""add is_active column to vault

Revision ID: ab75c2ab7dec
Revises: 0b905117c7ff
Create Date: 2024-05-22 13:08:29.627279

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab75c2ab7dec'
down_revision: Union[str, None] = '0b905117c7ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('vaults', sa.Column('is_active', sa.Boolean(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('vaults', 'is_active')
    # ### end Alembic commands ###
