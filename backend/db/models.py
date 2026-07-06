"""
SQLAlchemy models for the backend database.
"""

from shared.models import (
    AIContextMode,
    AIPurpose,
    ApplicationStatus,
    CloudType,
    ClusterStatus,
    MemberStatus,
    ResourceStatus,
    ResourceType,
    ScaleStopReason,
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
    Numeric,
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
    gitlab_user_id = Column(BigInteger, nullable=True, unique=True, index=True)

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN
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
    action = Column(String, nullable=False)
    resource_id = Column(Integer, ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    app_id = Column(Integer, ForeignKey("applications.id", ondelete="SET NULL"), nullable=True)
    cloud = Column(SQLEnum(CloudType), nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    ip_address = Column(String, nullable=True)
    extra = Column(JSON, nullable=True)

    user = relationship("User", back_populates="audit_logs")


# ── IDP entities ──────────────────────────────────────────────────────────────

class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)
    repo_url = Column(String, nullable=True, unique=True)
    owner = Column(String, nullable=False)
    gitlab_project_id = Column(BigInteger, nullable=True)
    owning_gitlab_group_id = Column(BigInteger, nullable=True)
    target_cluster_id = Column(Integer, ForeignKey("cluster_connections.id", ondelete="SET NULL"), nullable=True)
    origin = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    framework = Column(String, nullable=True)
    ci_injected = Column(Boolean, nullable=True)
    expose = Column(Boolean, nullable=True, default=False)
    last_pipeline_status = Column(String, nullable=True)
    last_known_status = Column(
        SQLEnum(ApplicationStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ApplicationStatus.ONBOARDING,
    )
    dev_scale_enabled = Column(Boolean, nullable=True, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)


class AppScaleState(Base):
    __tablename__ = "app_scale_states"

    id = Column(Integer, primary_key=True, index=True)
    app_id = Column(Integer, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True)
    env = Column(String, nullable=False)
    is_stopped = Column(Boolean, nullable=False, default=False)
    stop_reason = Column(
        SQLEnum(ScaleStopReason, values_callable=lambda x: [e.value for e in x]),
        nullable=True,
    )
    stopped_at = Column(DateTime(timezone=True), nullable=True)
    stopped_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resumed_at = Column(DateTime(timezone=True), nullable=True)
    resumed_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("app_id", "env", name="uq_app_scale_state_app_env"),
    )


class ClusterConnection(Base):
    __tablename__ = "cluster_connections"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    endpoint = Column(String, nullable=False)
    kubeconfig_secret_ref = Column(String, nullable=False)
    prometheus_url = Column(String, nullable=True)
    loki_url = Column(String, nullable=True)
    argocd_url = Column(String, nullable=True)
    status = Column(
        SQLEnum(ClusterStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ClusterStatus.UNKNOWN,
    )
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)


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
    username = Column(String, nullable=True)
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


# ── Alerting ──────────────────────────────────────────────────────────────────

class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    source = Column(String, nullable=False)
    app_id = Column(Integer, ForeignKey("applications.id", ondelete="SET NULL"), nullable=True)
    payload = Column(JSON, nullable=True)
    dedup_key = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    notifications = relationship("Notification", back_populates="event", cascade="all, delete-orphan")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    recipient_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    state = Column(String, nullable=False, default="new")
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    event = relationship("Event", back_populates="notifications")
    recipient = relationship("User")

    __table_args__ = (
        UniqueConstraint("event_id", "recipient_user_id", name="uq_notification_event_recipient"),
    )


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category = Column(String, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("user_id", "category", name="uq_notif_pref_user_category"),
    )


# ── AI assistant ──────────────────────────────────────────────────────────────

class AIAppSettings(Base):
    __tablename__ = "ai_app_settings"

    app_id = Column(Integer, ForeignKey("applications.id", ondelete="CASCADE"), primary_key=True)
    ai_enabled = Column(Boolean, nullable=False, default=False)
    ai_context_mode = Column(
        SQLEnum(AIContextMode, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=AIContextMode.METADATA_ONLY,
    )
    ai_security_scan_enabled = Column(Boolean, nullable=False, default=False)
    ai_security_summary_enabled = Column(Boolean, nullable=False, default=False)
    code_access_warning_accepted_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    code_access_warning_accepted_at = Column(DateTime(timezone=True), nullable=True)
    updated_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    application = relationship("Application")
    code_access_warning_accepted_by = relationship(
        "User", foreign_keys=[code_access_warning_accepted_by_user_id]
    )
    updated_by = relationship("User", foreign_keys=[updated_by_user_id])


class AIGlobalSettings(Base):
    """Singleton row (id=1): admin-managed runtime config for the AI assistant.

    When the row exists it overrides the env defaults (AI_ASSISTANT_ENABLED,
    AI_PROVIDER, AI_MODEL, AI_API_KEY, AI_PLATFORM_KB_ENABLED). Resolved on
    demand per request — never read at startup and never triggers a provider
    call by itself. api_key_encrypted is Fernet-encrypted and never returned
    nor logged.
    """
    __tablename__ = "ai_global_settings"

    id = Column(Integer, primary_key=True, default=1)
    assistant_enabled = Column(Boolean, nullable=True)  # null → env AI_ASSISTANT_ENABLED
    graphical_bot_enabled = Column(Boolean, nullable=False, default=True)
    platform_data_access_enabled = Column(Boolean, nullable=False, default=False)
    app_data_access_enabled = Column(Boolean, nullable=False, default=False)
    allowed_app_ids = Column(JSON, nullable=False, default=list)
    provider = Column(String, nullable=True)  # "mock" | "mistral" | "gemini" | "deepseek" — null → env
    model = Column(String, nullable=True)     # null → env AI_MODEL
    api_key_encrypted = Column(String, nullable=True)
    updated_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    updated_by = relationship("User", foreign_keys=[updated_by_user_id])


class AIUsageRecord(Base):
    __tablename__ = "ai_usage_records"

    id = Column(Integer, primary_key=True, index=True)
    app_id = Column(Integer, ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    provider = Column(String, nullable=False)
    model = Column(String, nullable=False)
    purpose = Column(
        SQLEnum(AIPurpose, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cache_hit_tokens = Column(Integer, nullable=False, default=0)
    cache_miss_tokens = Column(Integer, nullable=False, default=0)
    estimated_cost_usd = Column(Numeric(12, 8), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


# ── AI Security scans ─────────────────────────────────────────────────────────

class AISecurityScan(Base):
    __tablename__ = "ai_security_scans"

    id = Column(Integer, primary_key=True, index=True)
    app_id = Column(Integer, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True)
    ref = Column(String, nullable=False, default="main")
    status = Column(String, nullable=False, default="queued")
    triggered_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    gitlab_pipeline_id = Column(BigInteger, nullable=True)
    callback_token = Column(String, nullable=False, unique=True)
    error_message = Column(String, nullable=True)
    ai_summary_text = Column(String, nullable=True)
    ai_summarized_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)

    application = relationship("Application")
    triggered_by = relationship("User", foreign_keys=[triggered_by_user_id])
    findings = relationship("AISecurityFinding", back_populates="scan", cascade="all, delete-orphan")


class AISecurityFinding(Base):
    __tablename__ = "ai_security_findings"

    id = Column(Integer, primary_key=True, index=True)
    scan_id = Column(Integer, ForeignKey("ai_security_scans.id", ondelete="CASCADE"), nullable=False, index=True)
    tool = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    file_path = Column(String, nullable=True)
    line_start = Column(Integer, nullable=True)
    line_end = Column(Integer, nullable=True)
    confidence = Column(String, nullable=True)
    remediation = Column(String, nullable=True)
    status = Column(String, nullable=False, default="open")
    raw_data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    scan = relationship("AISecurityScan", back_populates="findings")


# ── Platform knowledge base (docs RAG) ────────────────────────────────────────

class PlatformDocChunk(Base):
    """A chunk of CNP documentation ingested for the platform assistant.

    Source content is redacted at ingestion; this table never stores source code
    or secrets — only curated documentation text used for grounded answers.
    """
    __tablename__ = "platform_doc_chunks"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String, nullable=False, default="local", index=True)
    path = Column(String, nullable=False, index=True)
    heading = Column(String, nullable=True)
    ordinal = Column(Integer, nullable=False, default=0)
    text = Column(String, nullable=False)
    token_count = Column(Integer, nullable=False, default=0)
    file_hash = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("source", "path", "ordinal", name="uq_platform_doc_chunk"),
    )
