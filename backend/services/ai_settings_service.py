"""Global AI assistant settings: singleton persistence and effective config.

The ai_global_settings row (admin-managed) overrides env defaults when it
exists. Resolution happens on demand in the assistant routes — never at
startup, and resolving a config never performs a provider/network call.

No imports from backend.api.*.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.crypto import decrypt_str, encrypt_str
from backend.db.models import AIGlobalSettings

# Providers pilotables depuis les réglages globaux admin
ALLOWED_PROVIDERS = ("mock", "mistral", "gemini", "deepseek")


@dataclass
class EffectiveAIConfig:
    """Runtime AI config after merging the DB row (if any) over env defaults."""

    provider_name: str
    model: str
    api_key: Optional[str]
    platform_kb_enabled: bool
    # Activation globale : réglage admin (DB) > env AI_ASSISTANT_ENABLED
    assistant_enabled: bool = False
    graphical_bot_enabled: bool = True
    # None tant qu'aucune ligne admin n'existe (comportement historique conservé)
    app_data_access_enabled: Optional[bool] = None
    allowed_app_ids: list[int] = field(default_factory=list)
    from_db: bool = False

    def app_allowed(self, app_id: int) -> bool:
        """Deny-by-default once admin settings exist: the app must be selected."""
        if not self.from_db:
            return True
        if not self.app_data_access_enabled:
            return False
        return app_id in self.allowed_app_ids


class AISettingsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_row(self) -> Optional[AIGlobalSettings]:
        result = await self.db.execute(
            select(AIGlobalSettings).where(AIGlobalSettings.id == 1)
        )
        return result.scalar_one_or_none()

    async def get_or_create_row(self) -> AIGlobalSettings:
        row = await self.get_row()
        if row is None:
            row = AIGlobalSettings(id=1)
            self.db.add(row)
        return row

    async def effective_config(self) -> EffectiveAIConfig:
        row = await self.get_row()
        if row is None:
            return EffectiveAIConfig(
                provider_name=settings.AI_PROVIDER,
                model=settings.AI_MODEL,
                api_key=settings.AI_API_KEY,
                platform_kb_enabled=settings.AI_PLATFORM_KB_ENABLED,
                assistant_enabled=settings.AI_ASSISTANT_ENABLED,
                graphical_bot_enabled=True,
                from_db=False,
            )

        # La clé stockée en DB ne s'applique qu'au provider choisi en DB ;
        # sans provider DB on retombe intégralement sur l'env.
        if row.provider:
            api_key = (
                decrypt_str(row.api_key_encrypted) if row.api_key_encrypted else None
            )
        else:
            api_key = settings.AI_API_KEY

        return EffectiveAIConfig(
            provider_name=row.provider or settings.AI_PROVIDER,
            model=row.model or settings.AI_MODEL,
            api_key=api_key,
            platform_kb_enabled=row.platform_data_access_enabled,
            assistant_enabled=(
                row.assistant_enabled
                if row.assistant_enabled is not None
                else settings.AI_ASSISTANT_ENABLED
            ),
            graphical_bot_enabled=row.graphical_bot_enabled,
            app_data_access_enabled=row.app_data_access_enabled,
            allowed_app_ids=list(row.allowed_app_ids or []),
            from_db=True,
        )

    @staticmethod
    def store_api_key(row: AIGlobalSettings, plaintext: str) -> None:
        row.api_key_encrypted = encrypt_str(plaintext)
