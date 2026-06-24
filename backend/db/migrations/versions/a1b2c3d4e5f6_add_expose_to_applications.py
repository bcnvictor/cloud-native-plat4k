"""Add expose column to applications

Revision ID: a1b2c3d4e5f6
Revises: c7d4f91a2b83
Create Date: 2026-06-23 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = 'a1b2c3d4e5f6'
down_revision = ('2bca4eddf11d', '333a1ce8b7ac', '2b2a5bb9d2f7')
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('applications', sa.Column('expose', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('applications', 'expose')
