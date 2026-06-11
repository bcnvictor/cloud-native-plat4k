"""Add slug column to applications

Revision ID: b5d1f3a8e260
Revises: 00114ca084ff
Create Date: 2026-06-11 00:00:00.000000

"""
import re

import sqlalchemy as sa
from alembic import op

revision = 'b5d1f3a8e260'
down_revision = '00114ca084ff'
branch_labels = None
depends_on = None


def _compute_slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9-]", "-", s)
    s = re.sub(r"-+", "-", s)
    s = s.strip("-")
    return s[:50]


def upgrade() -> None:
    op.add_column('applications', sa.Column('slug', sa.String(), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, name FROM applications")).fetchall()
    for row in rows:
        slug = _compute_slug(row[1])
        if not slug:
            slug = f"app-{row[0]}"
        conn.execute(
            sa.text("UPDATE applications SET slug = :slug WHERE id = :id"),
            {"slug": slug, "id": row[0]},
        )

    op.alter_column('applications', 'slug', nullable=False)
    op.create_unique_constraint('uq_applications_slug', 'applications', ['slug'])


def downgrade() -> None:
    op.drop_constraint('uq_applications_slug', 'applications', type_='unique')
    op.drop_column('applications', 'slug')
