"""GitLab authorization tiers (4K-67)

Revision ID: 333a1ce8b7ac
Revises: c5ead64c0fef
Create Date: 2026-06-15 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = '333a1ce8b7ac'
down_revision = 'c5ead64c0fef'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # is_admin flag on users (break-glass, always traced in audit log when used)
    op.add_column('users', sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='false'))

    # app_id on audit_logs to trace is_admin bypass per app
    op.add_column('audit_logs', sa.Column('app_id', sa.Integer(), sa.ForeignKey('applications.id', ondelete='SET NULL'), nullable=True))
    op.create_index('ix_audit_logs_app_id', 'audit_logs', ['app_id'])


def downgrade() -> None:
    op.drop_index('ix_audit_logs_app_id', table_name='audit_logs')
    op.drop_column('audit_logs', 'app_id')
    op.drop_column('users', 'is_admin')
