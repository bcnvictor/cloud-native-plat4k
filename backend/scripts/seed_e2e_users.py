"""Seed admin/dev users for the E2E (Playwright) test suite.

Run against a throwaway database before starting the backend for E2E:

    python -m backend.scripts.seed_e2e_users
"""
import asyncio

from shared.models import UserRole
from sqlalchemy import select

from backend.core.security import get_password_hash
from backend.db.models import Base, User
from backend.db.session import AsyncSessionLocal, engine

E2E_USERS = [
    ("admin-e2e@cnp.test", "AdminE2E123!", UserRole.ADMIN),
    ("dev-e2e@cnp.test", "DevE2E123!", UserRole.DEV),
]


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        for email, password, role in E2E_USERS:
            existing = await session.scalar(select(User).where(User.email == email))
            if existing:
                continue
            session.add(User(
                email=email,
                hashed_password=get_password_hash(password),
                role=role,
                is_active=True,
            ))
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
