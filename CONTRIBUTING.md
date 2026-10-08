# Contribuer à CNP

Ce guide s'adresse aux humains comme aux agents IA. Les instructions spécifiques aux agents sont dans [AGENTS.md](AGENTS.md), l'installation locale dans le [README](README.md).

## Workflow

- Une branche par sujet, PR vers `main`. Pas de push direct sur `main` hors hotfix.
- La CI (`.github/workflows/pipeline.yml`) doit être verte avant merge. Un push sur `main` déclenche le déploiement en prod uniquement si les jobs backend et frontend passent.

## Dépendances Python (backend / shared)

Les versions sont **figées** dans deux lockfiles générés, versionnés avec le code :

| Fichier | Contenu | Utilisé par |
|---|---|---|
| `backend/requirements.lock` | dépendances runtime | image Docker (prod) |
| `backend/requirements-dev.lock` | runtime + `test` + `dev` (pytest, ruff) | CI, dev local |

Les `pyproject.toml` déclarent **quoi** on dépend ; les locks fixent **quelle version exacte** est installée. Un même commit installe donc les mêmes versions en CI et en prod, quel que soit le jour du build.

### Règles

1. **Ajouter / retirer une dépendance** : l'éditer dans `backend/pyproject.toml` (ou `shared/pyproject.toml`), lancer `./scripts/lock-deps.sh`, committer `pyproject.toml` **et** les deux locks dans le même commit.
2. **Ne jamais éditer un `*.lock` à la main.** Ils sont toujours régénérés par `./scripts/lock-deps.sh`.
3. **Ne jamais se contenter d'un `pip install <paquet>`** pour faire marcher du code : si le code l'importe, il doit être déclaré dans un `pyproject.toml` puis verrouillé, sinon la CI et l'image Docker ne l'auront pas.
4. **Monter des versions** est un acte explicite, dans une PR dédiée testée par la CI :
   ```bash
   ./scripts/lock-deps.sh --upgrade-package sqlalchemy  # un paquet
   ./scripts/lock-deps.sh --upgrade                     # tout
   ```
5. **Conflit de merge sur un `*.lock`** : ne pas le résoudre ligne à ligne. Résoudre le conflit des `pyproject.toml`, prendre n'importe quelle version des locks, puis relancer `./scripts/lock-deps.sh`.
6. Une dépendance qui a des extras nécessaires au runtime doit les déclarer (ex. `sqlalchemy[asyncio]` pour `greenlet`, `uvicorn[standard]`).

`./scripts/lock-deps.sh` nécessite [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`). L'installation, elle, se fait avec pip :

```bash
python3 -m pip install -r backend/requirements-dev.lock
python3 -m pip install --no-deps -e ./shared -e ./backend
```

La CI échoue à l'étape *Check lockfiles are up to date* si les locks ne correspondent plus aux `pyproject.toml` ; le correctif est toujours `./scripts/lock-deps.sh` puis commit.

## Dépendances frontend

`frontend-new/package-lock.json` est versionné et la CI installe avec `npm ci`. Après `npm install <paquet>`, committer `package.json` **et** `package-lock.json`.
