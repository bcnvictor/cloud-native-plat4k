"""Re-encrypt credentials with dedicated ENCRYPTION_KEY

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-12 00:00:00.000000

"""
import base64
import os

from alembic import op
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import text

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def _derive_legacy_key(secret_key: str) -> bytes:
    return base64.urlsafe_b64encode(secret_key.encode('utf-8')[:32].ljust(32, b'0'))


def upgrade() -> None:
    encryption_key = os.environ.get("ENCRYPTION_KEY", "").strip()
    secret_key = os.environ.get("SECRET_KEY", "")

    if not encryption_key:
        return  # ENCRYPTION_KEY not configured yet; skip migration

    legacy_key = _derive_legacy_key(secret_key)
    if encryption_key.encode() == legacy_key:
        return  # Same key; nothing to do

    old_fernet = Fernet(legacy_key)
    new_fernet = Fernet(encryption_key.encode())

    conn = op.get_bind()
    rows = conn.execute(text("SELECT id, encrypted_credentials FROM cloud_credentials")).fetchall()
    for row in rows:
        try:
            plaintext = old_fernet.decrypt(row.encrypted_credentials.encode())
            new_encrypted = new_fernet.encrypt(plaintext).decode()
            conn.execute(
                text("UPDATE cloud_credentials SET encrypted_credentials = :enc WHERE id = :id"),
                {"enc": new_encrypted, "id": row.id},
            )
        except InvalidToken:
            # Already encrypted with new key or an unknown key; leave untouched
            pass


def downgrade() -> None:
    # Re-encryption is irreversible without the original key
    pass
