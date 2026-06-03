"""Add DEV role to userrole enum

Revision ID: b3e9f2a1d047
Revises: c7d4f91a2b83
Create Date: 2026-06-03 00:00:00.000000

"""
from alembic import op

revision = 'b3e9f2a1d047'
down_revision = 'c7d4f91a2b83'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'DEV'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; left as no-op.
    pass
