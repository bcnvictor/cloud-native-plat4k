"""Add ai_security_scans and ai_security_findings tables

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-06-30 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = 'd2e3f4a5b6c7'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'ai_security_scans',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('app_id', sa.Integer(), sa.ForeignKey('applications.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ref', sa.String(), nullable=False, server_default='main'),
        sa.Column('status', sa.String(), nullable=False, server_default='queued'),
        sa.Column('triggered_by_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('gitlab_pipeline_id', sa.BigInteger(), nullable=True),
        sa.Column('callback_token', sa.String(), nullable=False, unique=True),
        sa.Column('error_message', sa.String(), nullable=True),
        sa.Column('ai_summary_text', sa.Text(), nullable=True),
        sa.Column('ai_summarized_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    )
    op.create_index('ix_ai_security_scans_app_id', 'ai_security_scans', ['app_id'])
    op.create_index('ix_ai_security_scans_app_created', 'ai_security_scans', ['app_id', 'created_at'])

    op.create_table(
        'ai_security_findings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('scan_id', sa.Integer(), sa.ForeignKey('ai_security_scans.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tool', sa.String(), nullable=False),
        sa.Column('severity', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('file_path', sa.String(), nullable=True),
        sa.Column('line_start', sa.Integer(), nullable=True),
        sa.Column('line_end', sa.Integer(), nullable=True),
        sa.Column('confidence', sa.String(), nullable=True),
        sa.Column('remediation', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='open'),
        sa.Column('raw_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_ai_security_findings_scan_id', 'ai_security_findings', ['scan_id'])
    op.create_index('ix_ai_security_findings_scan_severity', 'ai_security_findings', ['scan_id', 'severity', 'status'])


def downgrade() -> None:
    op.drop_index('ix_ai_security_findings_scan_severity', table_name='ai_security_findings')
    op.drop_index('ix_ai_security_findings_scan_id', table_name='ai_security_findings')
    op.drop_table('ai_security_findings')
    op.drop_index('ix_ai_security_scans_app_created', table_name='ai_security_scans')
    op.drop_index('ix_ai_security_scans_app_id', table_name='ai_security_scans')
    op.drop_table('ai_security_scans')
