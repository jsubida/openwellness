"""initial

Proves the Alembic migration pattern end-to-end against the shared
JSONB-first table shape (`PGBaseEntity`) plus its `{table}_archive`
companion. `_pg_foundation_smoke` is a throwaway example table, not a
permanent one — Phase 3 drops/renames it once real entity migrations
replace it.

Revision ID: 0001
Revises:
Create Date: 2026-07-07 15:35:52.934984

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_shared_shape_table(name: str) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("data", JSONB(), nullable=False),
    )
    op.create_index(op.f(f"ix_{name}_owner"), name, ["owner"])


def upgrade() -> None:
    """Upgrade schema."""
    _create_shared_shape_table("_pg_foundation_smoke")
    _create_shared_shape_table("_pg_foundation_smoke_archive")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("_pg_foundation_smoke_archive")
    op.drop_table("_pg_foundation_smoke")
