# Templates de scaffolding CNP

Catalogue des templates d'applications utilisables comme point de départ d'un projet
CNP (ticket [4K-57](https://linear.app/sigl-4k/issue/4K-57)).

## Comment ça marche

Au scaffolding, la plateforme :

1. résout le template dans le groupe GitLab `GITLAB_TEMPLATES_NAMESPACE`
   (`4k-cnp-2027/cnp-templates/<nom>`) ;
2. copie tous les fichiers du repo template dans un nouveau repo applicatif ;
3. **génère** `chart/values.yaml` et `chart/Chart.yaml` à partir des paramètres
   fournis (nom, port, image, replicas, env…) — ces deux fichiers ne doivent donc
   **pas** être versionnés dans un template ;
4. **injecte** un `.gitlab-ci.yml` qui inclut `cnp-ci-modules/base/pipeline.yml` et le
   module framework adéquat. Un template ne doit donc **pas** contenir de
   `.gitlab-ci.yml` : l'injection échoue si le fichier existe déjà
   (`backend/ci/injector.py`).

Le contenu réel des templates vit dans GitLab, pas dans ce dépôt. Les dossiers
ci-dessous en sont la **source de staging** : on les pousse vers GitLab puis ils
servent de référence versionnée.

## Catalogue

| Template | Stack | Framework CI | Port | Détection (onboard/import) |
|----------|-------|--------------|------|----------------------------|
| [`node-express/`](node-express/) | Node.js / Express (API REST) | `nodejs` | 8000 | `package.json` |
| [`react-vite/`](react-vite/)     | React + Vite (SPA, servie par nginx) | `nodejs` | 8000 | `package.json` |
| [`go/`](go/)                     | Go (microservice, std lib) | `go` | 8000 | `go.mod` |

> Le template `python-fastapi` existe déjà dans `cnp-templates` (migré depuis ce dépôt
> au ticket 4K-31).

## Mapping framework

- **App scaffoldée** : la plateforme stocke le **nom du template** comme framework
  (`backend/services/app_service.py`). Le mapping nom de template → clé CI est fait
  dans `_FRAMEWORK_ALIASES` (`backend/ci/templates.py`) :
  `node-express → nodejs`, `react-vite → nodejs`, `go → go`.
- **App onboardée / importée** : le framework est détecté depuis les fichiers
  sentinelles du repo (`backend/ci/detector.py`).

Chaque clé CI (`nodejs`, `go`) correspond à un module `frameworks/<clé>.yml` dans
`cnp-ci-modules` (voir [`ci-modules/`](ci-modules/)).

## Déploiement des templates dans GitLab

Pour chaque dossier (`node-express`, `react-vite`, `go`), créer le repo GitLab
correspondant puis pousser le contenu **sans** `.git` :

```bash
# Exemple pour node-express
cd templates/node-express
git init -b main
git add .
git commit -m "feat(4K-57): node-express scaffolding template"
git remote add origin https://gitlab.com/4k-cnp-2027/cnp-templates/node-express.git
git push -u origin main
```

Les modules CI associés sont à pousser dans `cnp-ci-modules` — voir
[`ci-modules/README.md`](ci-modules/README.md).

## Validation E2E (critères d'acceptation 4K-57)

Une fois les repos poussés dans `cnp-templates`, ils apparaissent automatiquement dans
le sélecteur de templates de l'UI (page **New App → Scaffold**, alimentée par
`GET /apps/templates`). Le scaffolding n'est pas exposé par le CLI — il passe par l'UI
ou directement par l'API :

```bash
curl -X POST "$CNP_API/api/v1/apps/scaffold" \
  -H "X-API-Key: $CNP_API_KEY" -H "Content-Type: application/json" \
  -d '{"name":"demo-node","owner":"you","template":"node-express",
       "scaffolding":{"port":8000,"replicas":1}}'
```

Pour chaque template, vérifier que : le repo est créé dans `cnp-apps`, la CI passe au
vert (build Docker + job de test framework), l'image est poussée au registry, et le
repo GitOps est mis à jour.
