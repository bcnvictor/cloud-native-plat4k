"""Add ai_app_settings and ai_usage_records tables

Revision ID: c1d2e3f4a5b6
Revises: 857599f8e250
Create Date: 2026-06-30 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = 'c1d2e3f4a5b6'
down_revision = '857599f8e250'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'ai_app_settings',
        sa.Column('app_id', sa.Integer(), sa.ForeignKey('applications.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('ai_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            'ai_context_mode',
            sa.Enum('metadata_only', 'metadata_and_code', name='aicontextmode'),
            nullable=False,
            server_default='metadata_only',
        ),
        sa.Column('ai_security_scan_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('ai_security_summary_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            'code_access_warning_accepted_by_user_id',
            sa.Integer(),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('code_access_warning_accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'updated_by_user_id',
            sa.Integer(),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    op.create_table(
        'ai_usage_records',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('app_id', sa.Integer(), sa.ForeignKey('applications.id', ondelete='SET NULL'), nullable=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('model', sa.String(), nullable=False),
        sa.Column(
            'purpose',
            sa.Enum('chat', 'scan_summary', 'finops', 'incident', name='aipurpose'),
            nullable=False,
        ),
        sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cache_hit_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cache_miss_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('estimated_cost_usd', sa.Numeric(12, 8), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    op.create_index('ix_ai_usage_records_app_id', 'ai_usage_records', ['app_id'])
    op.create_index('ix_ai_usage_records_user_id', 'ai_usage_records', ['user_id'])
    op.create_index('ix_ai_usage_records_created_at', 'ai_usage_records', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_ai_usage_records_created_at', table_name='ai_usage_records')
    op.drop_index('ix_ai_usage_records_user_id', table_name='ai_usage_records')
    op.drop_index('ix_ai_usage_records_app_id', table_name='ai_usage_records')
    op.drop_table('ai_usage_records')
    op.drop_table('ai_app_settings')
    sa.Enum(name='aipurpose').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='aicontextmode').drop(op.get_bind(), checkfirst=True)
