"""Add Keycloak app-auth columns to applications

Revision ID: b1c2d3e4f5a6
Revises: 94488e983456
Create Date: 2026-09-24 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = 'b1c2d3e4f5a6'
down_revision = '94488e983456'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'applications',
        sa.Column('auth_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column('applications', sa.Column('auth_provisioned', sa.Boolean(), nullable=True))
    op.add_column('applications', sa.Column('auth_warnings', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('applications', 'auth_warnings')
    op.drop_column('applications', 'auth_provisioned')
    op.drop_column('applications', 'auth_enabled')
