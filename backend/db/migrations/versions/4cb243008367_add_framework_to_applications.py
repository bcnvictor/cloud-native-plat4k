"""Add framework column to applications

Revision ID: 4cb243008367
Revises: 0006
Create Date: 2026-05-28 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = '4cb243008367'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('applications', sa.Column('framework', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('applications', 'framework')
