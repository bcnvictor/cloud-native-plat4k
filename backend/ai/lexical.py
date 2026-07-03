"""Portable lexical retrieval (Okapi BM25) — no DB extension, no network.

Used to rank documentation chunks against a user question. Chosen over
Postgres tsvector / pgvector so the same ranking runs identically in prod
(Postgres) and in tests (SQLite), with zero external dependency. Embeddings /
pgvector can be layered on later without changing the calling code.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Sequence

_TOKEN_RE = re.compile(r"[0-9a-zàâäçéèêëîïôöùûüÿœæ]+", re.IGNORECASE)

# Very common FR/EN words that add noise to lexical matching.
_STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "ou", "à", "au",
    "aux", "en", "dans", "pour", "par", "sur", "avec", "sans", "que", "qui",
    "quoi", "quel", "quelle", "quels", "quelles", "est", "sont", "ce", "cette",
    "ces", "il", "elle", "je", "tu", "on", "se", "sa", "son", "ses", "mon",
    "ma", "mes", "the", "a", "an", "of", "and", "or", "to", "in", "on", "for",
    "is", "are", "be", "with", "what", "which", "how", "do", "does", "can",
}

_BM25_K1 = 1.5
_BM25_B = 0.75


def tokenize(text: str) -> list[str]:
    return [
        t for t in (m.group(0).lower() for m in _TOKEN_RE.finditer(text))
        if len(t) > 1 and t not in _STOPWORDS
    ]


def bm25_rank(query: str, documents: Sequence[str]) -> list[tuple[int, float]]:
    """Rank *documents* against *query*.

    Returns a list of (doc_index, score) sorted by descending score, excluding
    documents that share no query term (score 0). Empty when nothing matches.
    """
    q_terms = set(tokenize(query))
    if not q_terms or not documents:
        return []

    doc_tokens = [tokenize(d) for d in documents]
    doc_len = [len(dt) for dt in doc_tokens]
    n = len(documents)
    avgdl = (sum(doc_len) / n) if n else 0.0

    # document frequency per query term
    df: Counter[str] = Counter()
    for dt in doc_tokens:
        seen = set(dt)
        for term in q_terms:
            if term in seen:
                df[term] += 1

    scored: list[tuple[int, float]] = []
    for i, dt in enumerate(doc_tokens):
        if not dt:
            continue
        tf = Counter(dt)
        score = 0.0
        for term in q_terms:
            f = tf.get(term, 0)
            if f == 0:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            denom = f + _BM25_K1 * (1 - _BM25_B + _BM25_B * (doc_len[i] / avgdl if avgdl else 0))
            score += idf * (f * (_BM25_K1 + 1)) / denom
        if score > 0:
            scored.append((i, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored
