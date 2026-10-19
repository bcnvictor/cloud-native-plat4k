# ADR-0026 : Serveur MCP read-only

## Statut

Accepted : 2026-10-19 (4K-77)

## Contexte

Les développeurs veulent interroger la CNP depuis leur assistant IA (Claude Code, Cursor, VS Code…) sans installer d'outil. Le protocole MCP permet à ces clients de se brancher sur un serveur distant par simple URL. Le ticket 4K-77 demande un package indépendant `cnp-mcp`, exposé en HTTP, qui offre 6 tools en lecture : applications, déploiements, clusters et santé de la plateforme. La notion de « déploiement » n'existait pas dans l'API : seul `/apps/{id}/history` relayait l'historique ArgoCD d'une app.

## Décision

1. **Relais de la clé API de l'utilisateur, pas de clé de service.** Chaque client envoie sa clé CNP (`X-API-Key` ou `Authorization: Bearer`) ; `cnp-mcp` la relaie à l'API. `CNP_API_KEY` n'est qu'une clé de secours de dev local. Une clé de service unique aurait rendu les données lisibles par quiconque connaît l'URL publique, et l'audit ne verrait qu'un seul compte.
2. **`/mcp` sur le domaine existant, via le nginx du frontend.** Pas de sous-domaine ni de changement Cloudflare/DNS. nginx résout `cnp-mcp` à la requête : une panne du serveur MCP ne coupe pas l'UI.
3. **Endpoint backend `/api/v1/deployments` agrégé depuis l'historique ArgoCD, sans table.** La logique reste dans le backend (le MCP est un client fin) et la CLI en profite (`cnp deployments`). Chaque appel ArgoCD est limité à 4 s, l'endpoint à 8 s ; les sources en échec sont listées dans `unavailable` au lieu de faire échouer la requête.
4. **Transport streamable-http stateless avec réponses JSON** (`mcp` 2.3) : pas de session à conserver côté serveur et pas de flux SSE à faire passer par le tunnel.

## Conséquences

- L'historique est limité à la fenêtre d'ArgoCD (`revisionHistoryLimit`, 10 par défaut) ; un historique complet demandera une persistance (table + webhook ArgoCD).
- `initiated_by` vaut `null` pour les déploiements déclenchés par l'auto-sync ; l'auteur réel (commit déclencheur) fera l'objet d'un ticket de suivi.
- `/deployments` interroge ArgoCD à chaque appel (2 requêtes par app déployée), ce qui est acceptable à l'échelle actuelle de la plateforme.
- Pas d'OAuth 2.1 MCP : les clients qui ne savent pas envoyer de header passent par `mcp-remote`.
- Les réponses des tools partent chez le fournisseur du LLM de l'utilisateur ; `list_clusters` ne renvoie ni endpoint, ni référence Vault, ni URL interne.
