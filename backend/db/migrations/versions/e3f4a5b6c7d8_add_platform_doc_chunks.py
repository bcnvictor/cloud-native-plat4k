"""add platform_doc_chunks table (platform knowledge base)

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-07-01

Non-destructive: adds a single table used by the platform assistant to store
ingested CNP documentation chunks. Nothing references it unless
AI_PLATFORM_KB_ENABLED=true.
"""
import sqlalchemy as sa
from alembic import op

revision = 'e3f4a5b6c7d8'
down_revision = 'd2e3f4a5b6c7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'platform_doc_chunks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(), nullable=False, server_default='local'),
        sa.Column('path', sa.String(), nullable=False),
        sa.Column('heading', sa.String(), nullable=True),
        sa.Column('ordinal', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('text', sa.String(), nullable=False),
        sa.Column('token_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('file_hash', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source', 'path', 'ordinal', name='uq_platform_doc_chunk'),
    )
    op.create_index(op.f('ix_platform_doc_chunks_id'), 'platform_doc_chunks', ['id'], unique=False)
    op.create_index(op.f('ix_platform_doc_chunks_source'), 'platform_doc_chunks', ['source'], unique=False)
    op.create_index(op.f('ix_platform_doc_chunks_path'), 'platform_doc_chunks', ['path'], unique=False)
    op.create_index(op.f('ix_platform_doc_chunks_file_hash'), 'platform_doc_chunks', ['file_hash'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_platform_doc_chunks_file_hash'), table_name='platform_doc_chunks')
    op.drop_index(op.f('ix_platform_doc_chunks_path'), table_name='platform_doc_chunks')
    op.drop_index(op.f('ix_platform_doc_chunks_source'), table_name='platform_doc_chunks')
    op.drop_index(op.f('ix_platform_doc_chunks_id'), table_name='platform_doc_chunks')
    op.drop_table('platform_doc_chunks')
