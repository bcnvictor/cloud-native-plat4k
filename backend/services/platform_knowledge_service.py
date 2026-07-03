"""Platform knowledge base: ingest CNP docs and retrieve grounded chunks.

Ingestion is text-only (no LLM call), redacts secrets defensively, and is
idempotent via a per-file hash. Retrieval uses portable BM25 (backend.ai.lexical)
so it behaves identically on Postgres and SQLite.

The source is local markdown today (AI_PLATFORM_KB_DIR); switching to a
docs-only GitLab repo later only means changing how files are read here.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ai.lexical import bm25_rank
from backend.ai.redaction import redact
from backend.db.models import PlatformDocChunk


@dataclass
class RetrievedChunk:
    path: str
    heading: str | None
    text: str
    score: float

    @property
    def citation(self) -> str:
        return f"{self.path}#{self.heading}" if self.heading else self.path


@dataclass
class IngestStats:
    files_seen: int = 0
    files_indexed: int = 0
    files_skipped: int = 0
    chunks_written: int = 0


def _file_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_markdown(text: str, max_tokens: int = 400) -> list[tuple[str | None, str]]:
    """Split markdown into (heading, chunk_text) by section, capped at max_tokens.

    Sections start at any ``#``..``######`` heading. Long sections are further
    split on blank lines so no chunk grossly exceeds *max_tokens* (approx words).
    """
    lines = text.splitlines()
    sections: list[tuple[str | None, list[str]]] = []
    current_heading: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        if any(line.strip() for line in buffer):
            sections.append((current_heading, buffer.copy()))
        buffer.clear()

    for line in lines:
        if line.lstrip().startswith("#") and set(line.lstrip().split(" ", 1)[0]) == {"#"}:
            flush()
            current_heading = line.lstrip("# ").strip() or None
        else:
            buffer.append(line)
    flush()

    chunks: list[tuple[str | None, str]] = []
    for heading, body_lines in sections:
        body = "\n".join(body_lines).strip()
        if not body:
            continue
        if len(body.split()) <= max_tokens:
            chunks.append((heading, body))
            continue
        # Oversized section: pack paragraphs up to max_tokens, and hard-split any
        # single paragraph that alone exceeds max_tokens (e.g. no blank lines).
        para: list[str] = []
        count = 0
        for para_block in body.split("\n\n"):
            words = para_block.split()
            if len(words) > max_tokens:
                if para:
                    chunks.append((heading, "\n\n".join(para).strip()))
                    para, count = [], 0
                for i in range(0, len(words), max_tokens):
                    chunks.append((heading, " ".join(words[i:i + max_tokens])))
                continue
            if count + len(words) > max_tokens and para:
                chunks.append((heading, "\n\n".join(para).strip()))
                para, count = [], 0
            para.append(para_block)
            count += len(words)
        if para:
            chunks.append((heading, "\n\n".join(para).strip()))
    return chunks


class PlatformKnowledgeService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def ingest_local_dir(
        self,
        base_dir: str,
        *,
        source: str = "local",
        max_tokens: int = 400,
    ) -> IngestStats:
        """Ingest every ``*.md`` under *base_dir* into platform_doc_chunks."""
        stats = IngestStats()
        md_files: list[str] = []
        for root, _dirs, files in os.walk(base_dir):
            for name in files:
                if name.endswith(".md"):
                    md_files.append(os.path.join(root, name))

        for abs_path in sorted(md_files):
            stats.files_seen += 1
            rel_path = os.path.relpath(abs_path, base_dir)
            try:
                with open(abs_path, "r", encoding="utf-8") as fh:
                    raw = fh.read()
            except (OSError, UnicodeDecodeError):
                continue

            fhash = _file_hash(raw)
            existing = (
                await self.db.execute(
                    select(PlatformDocChunk.file_hash)
                    .where(PlatformDocChunk.source == source, PlatformDocChunk.path == rel_path)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if existing == fhash:
                stats.files_skipped += 1
                continue

            # File is new or changed: replace its chunks.
            await self.db.execute(
                delete(PlatformDocChunk).where(
                    PlatformDocChunk.source == source, PlatformDocChunk.path == rel_path
                )
            )
            for ordinal, (heading, body) in enumerate(chunk_markdown(raw, max_tokens)):
                safe = redact(body).text  # defense in depth — never store secrets
                self.db.add(
                    PlatformDocChunk(
                        source=source,
                        path=rel_path,
                        heading=heading,
                        ordinal=ordinal,
                        text=safe,
                        token_count=len(safe.split()),
                        file_hash=fhash,
                    )
                )
                stats.chunks_written += 1
            stats.files_indexed += 1

        await self.db.commit()
        return stats

    async def primer(
        self, paths: list[str], *, source: str = "local"
    ) -> list[RetrievedChunk]:
        """Return all chunks of the given curated page(s), in document order."""
        if not paths:
            return []
        rows = list(
            (
                await self.db.execute(
                    select(PlatformDocChunk)
                    .where(
                        PlatformDocChunk.source == source,
                        PlatformDocChunk.path.in_(paths),
                    )
                    .order_by(PlatformDocChunk.path, PlatformDocChunk.ordinal)
                )
            )
            .scalars()
            .all()
        )
        return [
            RetrievedChunk(path=r.path, heading=r.heading, text=r.text, score=0.0)
            for r in rows
        ]

    async def search(
        self, query: str, *, top_k: int = 6, source: str = "local"
    ) -> list[RetrievedChunk]:
        rows = list(
            (
                await self.db.execute(
                    select(PlatformDocChunk).where(PlatformDocChunk.source == source)
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            return []

        # Weight the section heading and file name (repeated) so that a chunk
        # titled e.g. "Le menu Settings" ranks above chunks that merely mention
        # the term in passing — headings/filenames carry strong topical signal.
        def _scoring_doc(r: PlatformDocChunk) -> str:
            heading = r.heading or ""
            stem = r.path.rsplit("/", 1)[-1].removesuffix(".md").replace("-", " ")
            return f"{heading} {heading} {stem} {r.text}"

        ranked = bm25_rank(query, [_scoring_doc(r) for r in rows])
        out: list[RetrievedChunk] = []
        for idx, score in ranked[:top_k]:
            r = rows[idx]
            out.append(RetrievedChunk(path=r.path, heading=r.heading, text=r.text, score=score))
        return out
