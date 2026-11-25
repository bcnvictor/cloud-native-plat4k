"""Add database_enabled to applications

Revision ID: c8d9e0f1a2b3
Revises: a7e1d0c4b288
Create Date: 2026-11-25 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = 'c8d9e0f1a2b3'
down_revision = 'a7e1d0c4b288'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'applications',
        sa.Column('database_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('applications', 'database_enabled')
