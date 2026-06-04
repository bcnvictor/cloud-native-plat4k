import base64
import json

from cryptography.fernet import Fernet
from shared.models import CloudType, CredentialCreate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.models import CloudCredential


def _build_fernet() -> Fernet:
    if settings.ENCRYPTION_KEY:
        return Fernet(settings.ENCRYPTION_KEY.encode())
    # Legacy fallback: derive from SECRET_KEY so existing deployments keep working
    key = base64.urlsafe_b64encode(settings.SECRET_KEY.encode('utf-8')[:32].ljust(32, b'0'))
    return Fernet(key)


class CredentialService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._fernet = _build_fernet()

    def _encrypt(self, data: dict) -> str:
        return self._fernet.encrypt(json.dumps(data).encode()).decode()

    def _decrypt(self, token: str) -> dict:
        return json.loads(self._fernet.decrypt(token.encode()).decode())

    async def get_credentials(self, user_id: int, cloud: CloudType) -> dict:
        result = await self.db.execute(
            select(CloudCredential).where(CloudCredential.user_id == user_id, CloudCredential.cloud == cloud)
        )
        cred = result.scalar_one_or_none()
        if not cred:
            return None
        return self._decrypt(cred.encrypted_credentials)

    async def add_credentials(self, user_id: int, payload: CredentialCreate) -> CloudCredential:
        encrypted = self._encrypt(payload.credentials)

        # Check if already exists, if so update
        result = await self.db.execute(
            select(CloudCredential).where(CloudCredential.user_id == user_id, CloudCredential.cloud == payload.cloud)
        )
        cred = result.scalar_one_or_none()
        if cred:
            cred.encrypted_credentials = encrypted
        else:
            cred = CloudCredential(user_id=user_id, cloud=payload.cloud, encrypted_credentials=encrypted)
            self.db.add(cred)

        await self.db.commit()
        await self.db.refresh(cred)
        return cred
