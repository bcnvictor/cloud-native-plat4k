"""Add sbom_snapshots + sbom_components: latest dependency inventory per application."""

import sqlalchemy as sa
from alembic import op

revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sbom_snapshots",
        sa.Column("app_id", sa.Integer(), sa.ForeignKey("applications.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("pipeline_id", sa.BigInteger(), nullable=False),
        sa.Column("commit_sha", sa.String(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("component_count", sa.Integer(), nullable=False),
        sa.Column("truncated", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_table(
        "sbom_components",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("app_id", sa.Integer(), sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("ecosystem", sa.String(), nullable=False),
        sa.Column("purl", sa.String(), nullable=False),
        sa.Column("direct", sa.Boolean(), nullable=True),
        sa.Column("licenses", sa.JSON(), nullable=False),
    )
    op.create_index("ix_sbom_components_app_id", "sbom_components", ["app_id"])
    op.create_index("ix_sbom_components_ecosystem_name", "sbom_components", ["ecosystem", "name"])
    op.create_index("ix_sbom_components_lower_name", "sbom_components", [sa.text("lower(name)")])


def downgrade():
    op.drop_index("ix_sbom_components_lower_name", table_name="sbom_components")
    op.drop_index("ix_sbom_components_ecosystem_name", table_name="sbom_components")
    op.drop_index("ix_sbom_components_app_id", table_name="sbom_components")
    op.drop_table("sbom_components")
    op.drop_table("sbom_snapshots")
