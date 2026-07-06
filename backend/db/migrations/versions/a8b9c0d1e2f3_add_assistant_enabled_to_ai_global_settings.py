"""add assistant_enabled to ai_global_settings (admin-managed activation)

Revision ID: a8b9c0d1e2f3
Revises: f4a5b6c7d8e9
Create Date: 2026-07-06

Non-destructive: nullable column, null keeps the env AI_ASSISTANT_ENABLED
behaviour. Lets admins enable/disable the assistant from the UI without
touching Vault or restarting the backend.
"""
import sqlalchemy as sa
from alembic import op

revision = 'a8b9c0d1e2f3'
down_revision = 'f4a5b6c7d8e9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'ai_global_settings',
        sa.Column('assistant_enabled', sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('ai_global_settings', 'assistant_enabled')
