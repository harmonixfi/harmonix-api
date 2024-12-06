"""add real_yield_v2 to vault category

Revision ID: e38a686b2086
Revises: fdcea60a9dbd
Create Date: 2024-12-02 13:49:03.411041

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e38a686b2086"
down_revision: Union[str, None] = "fdcea60a9dbd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Old and new enum values
old_categories = ["real_yield", "points", "rewards"]
new_categories = ["real_yield", "points", "rewards", "real_yield_v2"]


def upgrade() -> None:
    # Create a temporary enum type with the new value
    op.execute("ALTER TYPE vaultcategory ADD VALUE 'real_yield_v2'")


def downgrade() -> None:
    # Create a new enum without real_yield_v2
    op.execute("ALTER TYPE vaultcategory RENAME TO vaultcategory_old")
    op.execute("CREATE TYPE vaultcategory AS ENUM ('real_yield', 'points', 'rewards')")

    # Update existing records that might use real_yield_v2 to use real_yield
    op.execute(
        "ALTER TABLE vaults ALTER COLUMN category TYPE vaultcategory USING category::text::vaultcategory"
    )

    # Drop the old enum
    op.execute("DROP TYPE vaultcategory_old")
