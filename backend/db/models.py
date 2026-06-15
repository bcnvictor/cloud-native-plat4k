"""
SQLAlchemy models for the backend database.
"""

from shared.models import (
    ApplicationStatus,
    CloudType,
    ClusterStatus,
    DeploymentStatus,
    MemberStatus,
    ResourceStatus,
    ResourceType,
    UserRole,
)
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.DEV, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    gitlab_user_id = Column(BigInteger, nullable=True, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    credentials = relationship("CloudCredential", back_populates="user", cascade="all, delete-orphan")
    gitlab_credential = relationship("GitLabCredential", back_populates="user", uselist=False, cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user")


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    hashed_key = Column(String, nullable=False, unique=True)
    label = Column(String, nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    revoked = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="api_keys")


class Resource(Base):
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, index=True)
    cloud = Column(SQLEnum(CloudType), nullable=False, index=True)
    type = Column(SQLEnum(ResourceType), nullable=False, index=True)
    external_id = Column(String, nullable=False, index=True) # ID on the cloud provider
    name = Column(String, nullable=False)
    status = Column(SQLEnum(ResourceStatus), nullable=False, default=ResourceStatus.PENDING)
    metadata_ = Column("metadata", JSON, nullable=True) # JSON payload for extra data
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CloudCredential(Base):
    __tablename__ = "cloud_credentials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    cloud = Column(SQLEnum(CloudType), nullable=False)
    encrypted_credentials = Column(String, nullable=False) # In real world, use KMS or vault. Here we use Fernet encryption.
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="credentials")


class GitLabCredential(Base):
    __tablename__ = "gitlab_credentials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    encrypted_token = Column(String, nullable=False)
    encrypted_refresh_token = Column(String, nullable=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    namespace = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="gitlab_credential")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String, nullable=False) # e.g. "CREATE_RESOURCE", "DELETE_API_KEY"
    resource_id = Column(Integer, ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    app_id = Column(Integer, ForeignKey("applications.id", ondelete="SET NULL"), nullable=True)
    cloud = Column(SQLEnum(CloudType), nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    ip_address = Column(String, nullable=True)

    user = relationship("User", back_populates="audit_logs")


# ── IDP entities ──────────────────────────────────────────────────────────────

class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, unique=True)
    repo_url = Column(String, nullable=True, unique=True)
    owner = Column(String, nullable=False)
    gitlab_project_id = Column(BigInteger, nullable=True)
    owning_gitlab_group_id = Column(BigInteger, nullable=True)
    target_cluster_id = Column(Integer, ForeignKey("cluster_connections.id", ondelete="SET NULL"), nullable=True)
    origin = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    framework = Column(String, nullable=True)
    ci_injected = Column(Boolean, nullable=True)
    last_pipeline_status = Column(String, nullable=True)
    status = Column(
        SQLEnum(ApplicationStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ApplicationStatus.ONBOARDING,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    deployments = relationship("Deployment", back_populates="application", cascade="all, delete-orphan")


class ClusterConnection(Base):
    __tablename__ = "cluster_connections"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    endpoint = Column(String, nullable=False)
    kubeconfig_secret_ref = Column(String, nullable=False)
    status = Column(
        SQLEnum(ClusterStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ClusterStatus.UNKNOWN,
    )
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    deployments = relationship("Deployment", back_populates="cluster")


class Deployment(Base):
    __tablename__ = "deployments"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True)
    cluster_id = Column(Integer, ForeignKey("cluster_connections.id", ondelete="RESTRICT"), nullable=False, index=True)
    version = Column(String, nullable=False)
    status = Column(
        SQLEnum(DeploymentStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=DeploymentStatus.PENDING,
    )
    deployed_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    application = relationship("Application", back_populates="deployments")
    cluster = relationship("ClusterConnection", back_populates="deployments")


# ── GitLab membership mirror (ADR-0013) ───────────────────────────────────────

class GitLabGroup(Base):
    __tablename__ = "gitlab_groups"

    gitlab_group_id = Column(BigInteger, primary_key=True)
    name = Column(String, nullable=False)
    full_path = Column(String, nullable=False, unique=True)
    synced_at = Column(DateTime(timezone=True), nullable=True)

    members = relationship("GitLabGroupMember", back_populates="group", cascade="all, delete-orphan")


class GitLabGroupMember(Base):
    __tablename__ = "gitlab_group_members"

    id = Column(Integer, primary_key=True, index=True)
    gitlab_group_id = Column(BigInteger, ForeignKey("gitlab_groups.gitlab_group_id", ondelete="CASCADE"), nullable=False, index=True)
    gitlab_user_id = Column(BigInteger, nullable=True)
    access_level = Column(Integer, nullable=False)
    cnp_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(
        SQLEnum(MemberStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=MemberStatus.ACTIVE,
    )
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    group = relationship("GitLabGroup", back_populates="members")
    cnp_user = relationship("User")

    __table_args__ = (
        UniqueConstraint("gitlab_group_id", "gitlab_user_id", name="uq_group_member_gitlab_user"),
    )


class AppMember(Base):
    __tablename__ = "app_members"

    id = Column(Integer, primary_key=True, index=True)
    gitlab_project_id = Column(BigInteger, nullable=False, index=True)
    gitlab_user_id = Column(BigInteger, nullable=True)
    email = Column(String, nullable=True)
    access_level = Column(Integer, nullable=False)
    cnp_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(
        SQLEnum(MemberStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=MemberStatus.ACTIVE,
    )
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    cnp_user = relationship("User")

    __table_args__ = (
        UniqueConstraint("gitlab_project_id", "gitlab_user_id", name="uq_app_member_gitlab_user"),
        UniqueConstraint("gitlab_project_id", "email", name="uq_app_member_email"),
    )
