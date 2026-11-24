"""Add security_reports: latest CI security summary per application."""

import sqlalchemy as sa
from alembic import op

revision = "e4f5a6b7c8d9"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "security_reports",
        sa.Column(
            "app_id",
            sa.Integer(),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("pipeline_id", sa.BigInteger(), nullable=False),
        sa.Column("pipeline_url", sa.String(), nullable=False),
        sa.Column("commit_sha", sa.String(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )


def downgrade():
    op.drop_table("security_reports")
