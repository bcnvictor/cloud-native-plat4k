import os

# Must be set before any backend imports (Settings() runs at import time)
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32chars!")
os.environ.setdefault("POSTGRES_SERVER", "localhost")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("ENCRYPTION_KEY", "")
# Vault : adresse invalide intentionnelle — bootstrap_from_vault est mocké
# ci-dessous pour que les tests soient hermétiques (pas besoin d'un Vault réel).
os.environ.setdefault("VAULT_ADDR", "http://127.0.0.1:19999")
os.environ.setdefault("VAULT_TOKEN", "test-vault-token")
# Keep tests hermetic (no network) regardless of a local .env: force the mock
# LLM provider. The live integration test builds real providers directly, so
# it is unaffected by this.
os.environ.setdefault("AI_PROVIDER", "mock")

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from shared.models import UserRole
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.security import get_password_hash
from backend.db.models import Base, User
from backend.db.session import get_db
from backend.main import app

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def mock_vault_bootstrap():
    """No-op pour bootstrap_from_vault : rend tous les tests hermétiques
    vis-à-vis de Vault. Sans ce patch, le lifespan FastAPI tenterait de se
    connecter à Vault au premier appel client, ce qui échouerait en CI.
    """
    with patch("backend.core.config.bootstrap_from_vault", return_value=None):
        yield


@pytest.fixture
async def db_session():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def admin_user(db_session: AsyncSession) -> User:
    user = User(
        email="admin@test.com",
        hashed_password=get_password_hash("adminpass123"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def dev_user(db_session: AsyncSession) -> User:
    user = User(
        email="dev@test.com",
        hashed_password=get_password_hash("devpass123"),
        role=UserRole.DEV,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def admin_token(client: AsyncClient, admin_user: User) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "admin@test.com", "password": "adminpass123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
async def dev_token(client: AsyncClient, dev_user: User) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "dev@test.com", "password": "devpass123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]
