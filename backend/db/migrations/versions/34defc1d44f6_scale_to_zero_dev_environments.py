"""scale to zero dev environments

Revision ID: 34defc1d44f6
Revises: 857599f8e250
Create Date: 2026-07-02 14:44:29.892350

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '34defc1d44f6'
down_revision = '857599f8e250'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('applications', sa.Column('dev_scale_enabled', sa.Boolean(), nullable=True, server_default='true'))

    op.create_table(
        'app_scale_states',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('app_id', sa.Integer(), sa.ForeignKey('applications.id', ondelete='CASCADE'), nullable=False),
        sa.Column('env', sa.String(), nullable=False),
        sa.Column('is_stopped', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('stop_reason', sa.Enum('schedule', 'manual', name='scalestopreason'), nullable=True),
        sa.Column('stopped_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('stopped_by_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('resumed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resumed_by_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint('app_id', 'env', name='uq_app_scale_state_app_env'),
    )
    op.create_index('ix_app_scale_states_app_id', 'app_scale_states', ['app_id'])


def downgrade() -> None:
    op.drop_index('ix_app_scale_states_app_id', table_name='app_scale_states')
    op.drop_table('app_scale_states')
    op.execute('DROP TYPE IF EXISTS scalestopreason')
    op.drop_column('applications', 'dev_scale_enabled')
