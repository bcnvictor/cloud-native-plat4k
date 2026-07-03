"""Fernet encryption helpers shared by credential-storing features.

Same at-rest pattern as the GitLab PAT: ENCRYPTION_KEY when set, otherwise a
key derived from SECRET_KEY. Values are stored encrypted and never logged.
"""
import base64

from cryptography.fernet import Fernet

from backend.core.config import settings


def get_fernet() -> Fernet:
    if settings.ENCRYPTION_KEY:
        return Fernet(settings.ENCRYPTION_KEY.encode())
    key = base64.urlsafe_b64encode(settings.SECRET_KEY.encode()[:32].ljust(32, b"0"))
    return Fernet(key)


def encrypt_str(value: str) -> str:
    return get_fernet().encrypt(value.encode()).decode()


def decrypt_str(encrypted: str) -> str:
    return get_fernet().decrypt(encrypted.encode()).decode()
