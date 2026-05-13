"""
SQLAlchemy models for the backend database.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum as SQLEnum, JSON
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
from shared.models import CloudType, ResourceType, ResourceStatus, UserRole

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.VIEWER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
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
    cloud = Column(SQLEnum(CloudType), nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    ip_address = Column(String, nullable=True)

    user = relationship("User", back_populates="audit_logs")
