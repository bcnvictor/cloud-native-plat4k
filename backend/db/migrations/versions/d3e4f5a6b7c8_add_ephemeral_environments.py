"""Add ephemeral_environments (4K-286, ADR-0030)."""

import sqlalchemy as sa
from alembic import op

revision = "d3e4f5a6b7c8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ephemeral_environments",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("app_id", sa.Integer(), sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slug", sa.String(20), nullable=False),
        sa.Column("branch", sa.String(), nullable=False),
        sa.Column("cluster_name", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("provisioning", "active", "failed", "destroying", "destroyed", name="ephemeralenvstatus"),
            nullable=False,
        ),
        sa.Column("image_tag", sa.String(), nullable=True),
        sa.Column("pipeline_id", sa.BigInteger(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("destroyed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ephemeral_environments_app_id", "ephemeral_environments", ["app_id"])
    op.create_index(
        "uq_ephemeral_env_app_slug_alive",
        "ephemeral_environments",
        ["app_id", "slug"],
        unique=True,
        postgresql_where=sa.text("status <> 'destroyed'"),
    )


def downgrade():
    op.drop_index("uq_ephemeral_env_app_slug_alive", table_name="ephemeral_environments")
    op.drop_index("ix_ephemeral_environments_app_id", table_name="ephemeral_environments")
    op.drop_table("ephemeral_environments")
    op.execute("DROP TYPE IF EXISTS ephemeralenvstatus")
