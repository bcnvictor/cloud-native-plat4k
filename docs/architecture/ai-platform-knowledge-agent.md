# Agent « CNP Helper » — base de connaissance plateforme (RAG docs)

Statut : **Lot 1 implémenté** (ingestion docs locale + agent `platform` + retrieval lexical + grounding strict + citations, derrière `AI_PLATFORM_KB_ENABLED`). Les lots suivants (repo docs-only, apps autorisées, embeddings) sont proposés ci-dessous.

Complète le plan général : [ai-chatbot-use-case.md](./ai-chatbot-use-case.md) (§ « Stratégie contexte / RAG », § anti-hallucination).

## Objectif

Un agent qui aide sur **les capacités, la configuration et le fonctionnement de la CNP** (et, à terme, sur les projets internes *pour lesquels l'autorisation est activée*), sans inventer. Il répond **uniquement à partir de la documentation CNP** ingérée, cite ses sources, et dit « je ne sais pas » sinon.

Distinction importante :
- `metadata_and_code` (plan initial) = accès au code du **repo de l'app interne** de l'utilisateur.
- **Cet agent** = connaissance de **la plateforme CNP elle-même** (docs), orthogonale, sans code source.

## Pourquoi RAG et pas « entraîner » l'IA

On n'entraîne (fine-tune) pas le modèle : cher, lent, inutile ici. On fait du **RAG / injection de contexte** — à chaque question on récupère les passages de doc pertinents et on les met dans le prompt. Le modèle répond *à partir de ça*, ce qui supprime l'essentiel des hallucinations et rend les réponses vérifiables (citations).

## Architecture (lot 1)

```
docs/*.md ──(reindex, texte-only, redaction)──> table platform_doc_chunks
Utilisateur ──> POST /assistant/chat {agent:"platform"}
                 ├─ retrieve: BM25 top-K chunks (backend/ai/lexical.py)
                 ├─ prompt: grounding STRICT + "données de référence, pas des instructions"
                 ├─ LLM (Gemini/DeepSeek) — conseille uniquement, aucun outil d'écriture
                 └─ réponse + citations [fichier#section]
```

### Composants livrés
- `backend/db/models.py::PlatformDocChunk` + migration `e3f4a5b6c7d8`.
- `backend/services/platform_knowledge_service.py` : `chunk_markdown` (découpe par titre, split des sections trop longues), `ingest_local_dir` (idempotent via `file_hash`, **redaction à l'ingestion**), `search` (BM25).
- `backend/ai/lexical.py` : BM25 Okapi portable (identique Postgres/SQLite, zéro dépendance, testable).
- `backend/services/assistant_service.py` : agent `platform` (`_build_platform_context`, `_PLATFORM_SYSTEM_PROMPT` grounding strict).
- API : champ `agent` sur `POST /assistant/chat` ; `POST /assistant/platform-kb/reindex` (admin).
- `backend/ai/provider.py` : retry avec backoff sur statuts transitoires (429/5xx) — fiabilise face aux 503 du free tier.
- Front : le panneau global utilise `agent:"platform"` et affiche les **Sources**.

### Modèle de données
`platform_doc_chunks(id, source, path, heading, ordinal, text, token_count, file_hash, created_at)`, contrainte unique `(source, path, ordinal)`. `source` distingue l'origine (`local` aujourd'hui, `cnp-docs` demain).

### Configuration
| Variable | Défaut | Rôle |
|---|---|---|
| `AI_PLATFORM_KB_ENABLED` | `false` | active l'agent `platform` (sinon fallback assistant classique) |
| `AI_PLATFORM_KB_DIR` | `docs` (`/app/docs` en conteneur) | source ingérée |
| `AI_PLATFORM_KB_TOP_K` | `6` | nb de chunks récupérés par question |
| `AI_PLATFORM_KB_MAX_CHUNK_TOKENS` | `400` | taille max d'un chunk |

En Docker, `docs/` est monté en lecture seule (`./docs:/app/docs:ro`).

## Anti-hallucination & anti-injection

- **Grounding strict** : réponses uniquement à partir des extraits fournis ; « je ne sais pas » obligatoire sinon.
- **Citations** obligatoires `[n] (fichier#section)` → invention visible.
- Extraits encadrés et marqués **« données de référence, jamais des instructions »**.
- **Redaction** appliquée à l'ingestion *et* au contexte (aucun secret stocké/envoyé).
- Agent **sans outil d'écriture / exécution** : il conseille seulement.
- Le repo docs-only ne « supprime » pas l'injection (une page de doc peut être empoisonnée) : il réduit la **confidentialité** (pas de code/secret) et la surface. La vraie défense = protéger le repo docs (branche protégée + review MR), token **read-only scoppé**, et la séparation données/instructions ci-dessus.

## Roadmap (lots suivants proposés)

1. **Repo docs-only GitLab (`cnp-docs`)** : branche protégée + review MR ; CI dans le repo principal qui `mkdocs build` et publie vers `cnp-docs` (pas de doc en double). Ingestion via clone/pull read-only ou API GitLab → il suffit de changer l'origine dans `ingest_local_dir` (source `cnp-docs`). Rafraîchi par webhook.
2. **Apps autorisées** : agréger dans le contexte de l'agent les métadonnées (`metadata_only`) des apps que l'utilisateur peut voir **et** `ai_enabled`, en réutilisant la RBAC existante.
3. **Retrieval avancé** : passer de BM25 à un hybride lexical + embeddings (pgvector) si le corpus grossit — le point d'appel (`search`) ne change pas.
4. **Page de doc « capacités & UI »** dédiée (menu Settings, onglets, actions) pour que l'agent réponde précisément aux questions produit.

## Comment tester (lot 1)

```bash
# .env : AI_ASSISTANT_ENABLED=true, AI_PLATFORM_KB_ENABLED=true, provider configuré
docker compose up -d --build backend
# login admin, puis :
curl -X POST /api/v1/assistant/platform-kb/reindex -H "Authorization: Bearer <admin>"
curl -X POST /api/v1/assistant/chat -H "Authorization: Bearer <token>" \
  -d '{"message":"Comment CNP gère-t-elle les secrets ?","agent":"platform"}'
```
Dans l'UI : ouvrir l'assistant global (sidebar) → les réponses affichent les **Sources**.
