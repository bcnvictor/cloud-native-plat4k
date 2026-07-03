"""Tests for platform knowledge ingestion + retrieval + the platform agent."""

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32chars!")
os.environ.setdefault("POSTGRES_SERVER", "localhost")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("ENCRYPTION_KEY", "")
os.environ.setdefault("VAULT_ADDR", "http://127.0.0.1:19999")
os.environ.setdefault("VAULT_TOKEN", "test-vault-token")

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.models import PlatformDocChunk
from backend.services.platform_knowledge_service import (
    PlatformKnowledgeService,
    chunk_markdown,
)


# ── chunking ─────────────────────────────────────────────────────────────────


def test_chunk_markdown_splits_by_heading():
    md = "# Titre\n\nIntro.\n\n## Settings\n\nOptions du menu.\n\n## FinOps\n\nCoûts."
    chunks = chunk_markdown(md)
    headings = [h for h, _ in chunks]
    assert "Settings" in headings
    assert "FinOps" in headings
    settings_chunk = next(t for h, t in chunks if h == "Settings")
    assert "Options du menu" in settings_chunk


def test_chunk_markdown_splits_oversized_section():
    body = " ".join(f"mot{i}" for i in range(1000))
    md = f"## Grosse section\n\n{body}"
    chunks = chunk_markdown(md, max_tokens=100)
    assert len(chunks) > 1
    assert all(h == "Grosse section" for h, _ in chunks)


# ── ingestion ────────────────────────────────────────────────────────────────


def _write_docs(tmp_path):
    (tmp_path / "settings.md").write_text(
        "# Settings\n\nLe menu Settings contient l'URL publique et la connexion GitLab.\n",
        encoding="utf-8",
    )
    sub = tmp_path / "guides"
    sub.mkdir()
    (sub / "finops.md").write_text(
        "# FinOps\n\nLa page FinOps affiche les coûts CPU et RAM sur 30 jours.\n",
        encoding="utf-8",
    )


@pytest.mark.anyio
async def test_ingest_indexes_files(db_session: AsyncSession, tmp_path):
    _write_docs(tmp_path)
    stats = await PlatformKnowledgeService(db_session).ingest_local_dir(str(tmp_path))
    assert stats.files_seen == 2
    assert stats.files_indexed == 2
    assert stats.chunks_written >= 2

    rows = (await db_session.execute(select(PlatformDocChunk))).scalars().all()
    paths = {r.path for r in rows}
    assert "settings.md" in paths
    assert os.path.join("guides", "finops.md") in paths


@pytest.mark.anyio
async def test_ingest_is_idempotent(db_session: AsyncSession, tmp_path):
    _write_docs(tmp_path)
    svc = PlatformKnowledgeService(db_session)
    await svc.ingest_local_dir(str(tmp_path))
    stats2 = await svc.ingest_local_dir(str(tmp_path))
    # unchanged files are skipped, no new chunks
    assert stats2.files_skipped == 2
    assert stats2.files_indexed == 0
    assert stats2.chunks_written == 0


@pytest.mark.anyio
async def test_ingest_redacts_secrets(db_session: AsyncSession, tmp_path):
    (tmp_path / "leak.md").write_text(
        "# Config\n\nExemple de token: glpat-abcdefghij1234567890 à ne pas exposer.\n",
        encoding="utf-8",
    )
    await PlatformKnowledgeService(db_session).ingest_local_dir(str(tmp_path))
    rows = (await db_session.execute(select(PlatformDocChunk))).scalars().all()
    joined = "\n".join(r.text for r in rows)
    assert "glpat-abcdefghij1234567890" not in joined
    assert "[REDACTED:gitlab-token]" in joined


# ── retrieval ────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_search_returns_relevant_chunk(db_session: AsyncSession, tmp_path):
    _write_docs(tmp_path)
    svc = PlatformKnowledgeService(db_session)
    await svc.ingest_local_dir(str(tmp_path))
    results = await svc.search("Quelles options dans le menu Settings ?", top_k=3)
    assert results
    assert results[0].path == "settings.md"
    assert results[0].citation.startswith("settings.md")


# ── platform agent via endpoint ──────────────────────────────────────────────


@pytest.mark.anyio
async def test_primer_returns_page_chunks(db_session: AsyncSession, tmp_path):
    _write_docs(tmp_path)
    svc = PlatformKnowledgeService(db_session)
    await svc.ingest_local_dir(str(tmp_path))
    chunks = await svc.primer(["settings.md"])
    assert chunks
    assert all(c.path == "settings.md" for c in chunks)


@pytest.mark.anyio
async def test_platform_chat_always_injects_primer(
    client: AsyncClient, admin_token: str, db_session: AsyncSession, tmp_path
):
    _write_docs(tmp_path)
    await PlatformKnowledgeService(db_session).ingest_local_dir(str(tmp_path))

    with (
        patch.object(settings, "AI_ASSISTANT_ENABLED", True),
        patch.object(settings, "AI_PLATFORM_KB_ENABLED", True),
        patch.object(settings, "AI_PLATFORM_KB_PRIMER_PATHS", "settings.md"),
    ):
        # A question unrelated to Settings must still carry the primer page.
        resp = await client.post(
            "/api/v1/assistant/chat",
            json={"message": "Parle-moi des coûts FinOps.", "agent": "platform"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 200
    refs = [c.get("ref", "") for c in resp.json()["citations"]]
    assert any(r.startswith("settings.md") for r in refs)


@pytest.mark.anyio
async def test_platform_chat_uses_docs_and_returns_citations(
    client: AsyncClient, admin_token: str, db_session: AsyncSession, tmp_path
):
    _write_docs(tmp_path)
    await PlatformKnowledgeService(db_session).ingest_local_dir(str(tmp_path))

    with (
        patch.object(settings, "AI_ASSISTANT_ENABLED", True),
        patch.object(settings, "AI_PLATFORM_KB_ENABLED", True),
    ):
        resp = await client.post(
            "/api/v1/assistant/chat",
            json={"message": "Quelles options dans le menu Settings ?", "agent": "platform"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "search_platform_docs" in data["used_tools"]
    assert any(c.get("type") == "doc" for c in data["citations"])


@pytest.mark.anyio
async def test_platform_agent_ignored_when_kb_disabled(
    client: AsyncClient, admin_token: str
):
    with (
        patch.object(settings, "AI_ASSISTANT_ENABLED", True),
        patch.object(settings, "AI_PLATFORM_KB_ENABLED", False),
    ):
        resp = await client.post(
            "/api/v1/assistant/chat",
            json={"message": "Hello", "agent": "platform"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 200
    # falls back to the default global assistant — no doc retrieval tool
    assert "search_platform_docs" not in resp.json()["used_tools"]


@pytest.mark.anyio
async def test_reindex_requires_admin_and_kb_enabled(
    client: AsyncClient, admin_token: str, tmp_path
):
    _write_docs(tmp_path)
    with (
        patch.object(settings, "AI_ASSISTANT_ENABLED", True),
        patch.object(settings, "AI_PLATFORM_KB_ENABLED", True),
        patch.object(settings, "AI_PLATFORM_KB_DIR", str(tmp_path)),
    ):
        resp = await client.post(
            "/api/v1/assistant/platform-kb/reindex",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 200
    assert resp.json()["files_indexed"] == 2
