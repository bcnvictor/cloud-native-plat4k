"""Add ci_injected column to applications

Revision ID: fa5e6a11f864
Revises: 4cb243008367
Create Date: 2026-05-28 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = 'fa5e6a11f864'
down_revision = '4cb243008367'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('applications', sa.Column('ci_injected', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('applications', 'ci_injected')
