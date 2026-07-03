"""add ai_global_settings singleton table (admin AI assistant settings)

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-07-02

Non-destructive: adds a single singleton table read on demand by the assistant
routes. Nothing changes while AI_ASSISTANT_ENABLED=false and no row exists.
"""
from alembic import op
import sqlalchemy as sa

revision = 'f4a5b6c7d8e9'
down_revision = 'e3f4a5b6c7d8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'ai_global_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('platform_data_access_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('app_data_access_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('allowed_app_ids', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('provider', sa.String(), nullable=True),
        sa.Column('model', sa.String(), nullable=True),
        sa.Column('api_key_encrypted', sa.String(), nullable=True),
        sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('ai_global_settings')
