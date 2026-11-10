"""Register per-cluster Keycloak instances without changing existing identities."""

import sqlalchemy as sa
from alembic import op

revision = "c2d3e4f5a6b7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "keycloak_instances",
        sa.Column("instance_key", sa.String(63), primary_key=True),
        sa.Column(
            "cluster_id",
            sa.Integer(),
            sa.ForeignKey("cluster_connections.id", ondelete="SET NULL"),
            unique=True,
        ),
        sa.Column("public_url", sa.String(), nullable=False),
        sa.Column("admin_url", sa.String(), nullable=False),
        sa.Column("admin_client_id", sa.String(), nullable=False),
        sa.Column("provisioner_secret_ref", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.add_column("applications", sa.Column("auth_instance_key", sa.String(63), nullable=True))
    op.create_foreign_key(
        "fk_application_auth_instance",
        "applications",
        "keycloak_instances",
        ["auth_instance_key"],
        ["instance_key"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_applications_auth_instance_key", "applications", ["auth_instance_key"])


def downgrade():
    op.drop_index("ix_applications_auth_instance_key", table_name="applications")
    op.drop_constraint("fk_application_auth_instance", "applications", type_="foreignkey")
    op.drop_column("applications", "auth_instance_key")
    op.drop_table("keycloak_instances")
