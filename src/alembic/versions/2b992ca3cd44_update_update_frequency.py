"""update update_frequency

Revision ID: 2b992ca3cd44
Revises: 4958d1d6c7fb
Create Date: 2024-08-23 11:42:25.759434

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '2b992ca3cd44'
down_revision: Union[str, None] = '4958d1d6c7fb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('vaults', sa.Column('update_frequency', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('vaults', 'update_frequency')
    # ### end Alembic commands ###
