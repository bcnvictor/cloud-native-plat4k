import asyncio
import sys

# Add /app directory to sys.path
sys.path.append("/app")

from shared.models import UserRole
from sqlalchemy import select

from backend.core.security import get_password_hash
from backend.db.models import User
from backend.db.session import AsyncSessionLocal


async def seed_admin():
    async with AsyncSessionLocal() as session:
        email = "admin@4k.com"
        password = "admin"
        
        result = await session.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none():
            print(f"User {email} already exists")
            return

        admin = User(
            email=email,
            hashed_password=get_password_hash(password),
            role=UserRole.ADMIN,
            is_active=True
        )
        session.add(admin)
        await session.commit()
        print(f"User {email} created successfully")

if __name__ == "__main__":
    asyncio.run(seed_admin())
