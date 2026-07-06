"""add graphical bot display setting to ai_global_settings

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-07-06

Non-destructive: existing platforms keep the graphical assistant bot visible
until an admin disables it from the global AI assistant settings.
"""
import sqlalchemy as sa
from alembic import op

revision = 'b9c0d1e2f3a4'
down_revision = 'a8b9c0d1e2f3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'ai_global_settings',
        sa.Column(
            'graphical_bot_enabled',
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column('ai_global_settings', 'graphical_bot_enabled')
