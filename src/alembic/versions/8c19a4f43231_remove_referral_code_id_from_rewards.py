"""Remove referral_code_id from rewards

Revision ID: 8c19a4f43231
Revises: de64a096d467
Create Date: 2024-07-29 19:53:00.482112

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c19a4f43231'
down_revision: Union[str, None] = 'de64a096d467'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint('rewards_referral_code_id_fkey', 'rewards', type_='foreignkey')
    op.drop_column('rewards', 'referral_code_id')
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('rewards', sa.Column('referral_code_id', sa.UUID(), autoincrement=False, nullable=False))
    op.create_foreign_key('rewards_referral_code_id_fkey', 'rewards', 'referral_codes', ['referral_code_id'], ['referral_code_id'])
    # ### end Alembic commands ###
