"""Add refresh token fields to gitlab_credentials

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('gitlab_credentials', sa.Column('encrypted_refresh_token', sa.String(), nullable=True))
    op.add_column('gitlab_credentials', sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('gitlab_credentials', 'token_expires_at')
    op.drop_column('gitlab_credentials', 'encrypted_refresh_token')
