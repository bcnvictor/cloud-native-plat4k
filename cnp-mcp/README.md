# cnp-mcp — serveur MCP read-only de la CNP

Expose les données de la plateforme (applications, déploiements, clusters, santé) à tout client IA compatible [MCP](https://modelcontextprotocol.io) : Claude Code, Cursor, VS Code, Claude Desktop… Aucune installation locale : on configure une URL et sa clé API CNP.

- URL : `https://cnp.cloud-native-plat4k.me/mcp` (transport streamable-http)
- Lecture seule : 6 tools, tous annotés `readOnlyHint`.
- Chaque requête utilise **la clé API CNP de l'utilisateur** : il ne voit que ce que l'API lui permet de voir, et la révocation se fait dans l'UI (Profil → Clés API).

## Tools

| Tool | Description |
|---|---|
| `list_apps` | Applications avec statut, owner, framework, cluster cible |
| `get_app(app_id)` | Fiche complète d'une application |
| `list_deployments(app_id?, env?, limit?)` | Déploiements récents (historique ArgoCD, ~10 par app et par env) |
| `get_deployment(deployment_id)` | Un déploiement (`<app_id>:<dev\|prod>:<history_id>`) |
| `list_clusters` | Clusters, statut et intégrations (sans endpoint ni secret) |
| `get_platform_health` | Synthèse : API, base, clusters offline, apps dégradées |

`initiated_by` vaut `null` (affiché `auto`) pour un déploiement déclenché par l'auto-sync ArgoCD.

## Configurer son client

1. Créer une clé dans l'UI CNP (Profil → Clés API), par exemple « MCP ».
2. Déclarer le serveur :

**Claude Code**

```bash
claude mcp add --transport http cnp https://cnp.cloud-native-plat4k.me/mcp --header "X-API-Key: <clé>"
```

**Cursor / VS Code** (`mcp.json`)

```json
{
  "servers": {
    "cnp": {
      "type": "http",
      "url": "https://cnp.cloud-native-plat4k.me/mcp",
      "headers": { "X-API-Key": "<clé>" }
    }
  }
}
```

**Claude Desktop** (via `mcp-remote`)

```json
{
  "mcpServers": {
    "cnp": {
      "command": "npx",
      "args": ["mcp-remote", "https://cnp.cloud-native-plat4k.me/mcp", "--header", "X-API-Key:<clé>"]
    }
  }
}
```

`Authorization: Bearer <clé>` est aussi accepté, avec une **clé API CNP**, pas un JWT de session.

> Les réponses des tools sont transmises au fournisseur du LLM de votre client (noms d'apps, owners, statuts). Aucun secret n'est exposé : pas d'endpoint de cluster, pas de référence Vault, pas d'URL interne.

## Variables d'environnement

| Variable | Obligatoire | Rôle |
|---|---|---|
| `CNP_API_URL` | oui | Base de l'API, ex. `http://backend:8000/api/v1` |
| `CNP_API_KEY` | non | Clé de secours pour les requêtes sans clé, **dev local uniquement** (WARNING au démarrage). Jamais en prod. |
| `MCP_ALLOWED_HOSTS` | non | Hosts acceptés (anti DNS-rebinding), séparés par des virgules ; chaque host accepte aussi tout port. Défaut `localhost,127.0.0.1`. |
| `MCP_PORT` | non | Défaut `8080`. |

## Développement local

```bash
python3 -m venv cnp-mcp/.venv
cnp-mcp/.venv/bin/pip install -r cnp-mcp/requirements-dev.lock
cnp-mcp/.venv/bin/pip install --no-deps -e ./cnp-mcp
cnp-mcp/.venv/bin/pytest cnp-mcp/tests/ -v
CNP_API_URL=http://localhost:8000/api/v1 CNP_API_KEY=<clé locale> cnp-mcp/.venv/bin/cnp-mcp
claude mcp add --transport http cnp-local http://localhost:8080/mcp
```

Dans la stack Docker (`./start.sh`), le service `cnp-mcp` est joignable via `http://localhost/mcp`.

Dépendances : modifier `pyproject.toml`, puis `./scripts/lock-deps.sh`, et committer les lockfiles (voir `CONTRIBUTING.md`).
