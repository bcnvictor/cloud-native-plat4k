"""Unit tests for BM25 lexical ranking — no DB, no network."""

from backend.ai.lexical import bm25_rank, tokenize


def test_tokenize_drops_stopwords_and_short_tokens():
    toks = tokenize("Quelles sont les options du menu Settings ?")
    assert "options" in toks
    assert "menu" in toks
    assert "settings" in toks
    assert "les" not in toks  # stopword
    assert "du" not in toks


def test_bm25_ranks_relevant_document_first():
    docs = [
        "Le menu Settings contient les options de connexion GitLab et l'URL publique.",
        "La facturation FinOps calcule les coûts CPU et RAM sur 30 jours.",
        "Les clusters Kubernetes sont enregistrés via la page Clusters.",
    ]
    ranked = bm25_rank("Quelles options dans le menu Settings ?", docs)
    assert ranked, "expected at least one match"
    assert ranked[0][0] == 0  # the Settings doc ranks first


def test_bm25_no_match_returns_empty():
    docs = ["documentation sur les clusters", "guide de déploiement"]
    assert bm25_rank("xyzzy plugh", docs) == []


def test_bm25_empty_query_or_docs():
    assert bm25_rank("", ["a b c"]) == []
    assert bm25_rank("query", []) == []
