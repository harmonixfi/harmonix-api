"""add unique depositors vault performance

Revision ID: 7fb80eb63831
Revises: 0059b470deb7
Create Date: 2024-06-06 17:25:12.401191

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7fb80eb63831'
down_revision: Union[str, None] = '0059b470deb7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('vault_performance', sa.Column('unique_depositors', sa.Integer(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('vault_performance', 'unique_depositors')
    # ### end Alembic commands ###