"""add last_pipeline_status to applications

Revision ID: c7d4f91a2b83
Revises: fa5e6a11f864
Create Date: 2026-05-29

"""
from alembic import op
import sqlalchemy as sa

revision = 'c7d4f91a2b83'
down_revision = 'fa5e6a11f864'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('applications', sa.Column('last_pipeline_status', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('applications', 'last_pipeline_status')
