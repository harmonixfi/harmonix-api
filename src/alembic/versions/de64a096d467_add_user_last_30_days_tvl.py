"""Add user_last_30_days_tvl

Revision ID: de64a096d467
Revises: 6375e63f1755
Create Date: 2024-07-24 14:06:41.354639

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = 'de64a096d467'
down_revision: Union[str, None] = '6375e63f1755'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('user_last_30_days_tvl',
    sa.Column('id', sqlmodel.sql.sqltypes.GUID(), nullable=False),
    sa.Column('user_id', sqlmodel.sql.sqltypes.GUID(), nullable=False),
    sa.Column('avg_entry_price', sa.Float(), nullable=False),
    sa.Column('shares_deposited', sa.Float(), nullable=False),
    sa.Column('shares_withdraw', sa.Float(), nullable=False),
    sa.Column('total_value_locked', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.drop_index('ix_user_monthly_tvl_month', table_name='user_monthly_tvl')
    op.drop_table('user_monthly_tvl')
    op.drop_table('userstoupdate')
    op.alter_column('campaigns', 'start_date',
               existing_type=postgresql.TIMESTAMP(),
               nullable=True)
    op.create_index(op.f('ix_rewards_campaign_name'), 'rewards', ['campaign_name'], unique=False)
    op.create_index(op.f('ix_user_holding_asset_history_chain'), 'user_holding_asset_history', ['chain'], unique=False)
    op.create_index(op.f('ix_users_tier'), 'users', ['tier'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_users_tier'), table_name='users')
    op.drop_index(op.f('ix_user_holding_asset_history_chain'), table_name='user_holding_asset_history')
    op.drop_index(op.f('ix_rewards_campaign_name'), table_name='rewards')
    op.alter_column('campaigns', 'start_date',
               existing_type=postgresql.TIMESTAMP(),
               nullable=True)
    op.create_table('userstoupdate',
    sa.Column('user_id', sa.UUID(), autoincrement=False, nullable=True),
    sa.Column('wallet_address', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('tier', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True)
    )
    op.create_table('user_monthly_tvl',
    sa.Column('id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('user_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('month', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
    sa.Column('total_value_locked', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
    sa.PrimaryKeyConstraint('id', name='user_monthly_tvl_pkey')
    )
    op.create_index('ix_user_monthly_tvl_month', 'user_monthly_tvl', ['month'], unique=False)
    op.drop_table('user_last_30_days_tvl')
    # ### end Alembic commands ###