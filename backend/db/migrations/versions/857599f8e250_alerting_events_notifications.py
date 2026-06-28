"""alerting: events, notifications, notification_preferences, audit_log.extra

Revision ID: 857599f8e250
Revises: 9b7c6d5e4f3a
Create Date: 2026-06-28 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = '857599f8e250'
down_revision = '9b7c6d5e4f3a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── AuditLog enrichment ───────────────────────────────────────────────────
    op.add_column('audit_logs', sa.Column('extra', sa.JSON(), nullable=True))

    # ── events ────────────────────────────────────────────────────────────────
    op.create_table(
        'events',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('severity', sa.String(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('app_id', sa.Integer(), sa.ForeignKey('applications.id', ondelete='SET NULL'), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('dedup_key', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_events_dedup_key', 'events', ['dedup_key'])

    # ── notifications ─────────────────────────────────────────────────────────
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('event_id', sa.Integer(), sa.ForeignKey('events.id', ondelete='CASCADE'), nullable=False),
        sa.Column('recipient_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('state', sa.String(), nullable=False, server_default='new'),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('event_id', 'recipient_user_id', name='uq_notification_event_recipient'),
    )
    op.create_index('ix_notifications_recipient_state', 'notifications', ['recipient_user_id', 'state'])

    # ── notification_preferences ──────────────────────────────────────────────
    op.create_table(
        'notification_preferences',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.UniqueConstraint('user_id', 'category', name='uq_notif_pref_user_category'),
    )


def downgrade() -> None:
    op.drop_table('notification_preferences')
    op.drop_index('ix_notifications_recipient_state', table_name='notifications')
    op.drop_table('notifications')
    op.drop_index('ix_events_dedup_key', table_name='events')
    op.drop_table('events')
    op.drop_column('audit_logs', 'extra')
