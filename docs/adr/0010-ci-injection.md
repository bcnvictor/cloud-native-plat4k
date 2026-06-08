# ADR-0010 : Injection automatique de pipeline CI dans les repos applicatifs

## Statut

Accepted
- Date : 2026-05-28


## Contexte

Lors de l'enregistrement d'une application sur CNP (scaffoldée ou importée), la plateforme doit garantir qu'un pipeline CI baseline est en place dans le repo GitLab correspondant. Sans injection automatique, chaque équipe devrait configurer manuellement sa CI, ce qui nuit à la standardisation de la sécurité (hadolint, gitleaks, trivy) et à l'observabilité de la plateforme.

Deux types d'apps existent :
- `scaffolded` : le repo est créé par CNP, vierge — on peut pousser directement sur `main`
- `imported` : le repo préexiste avec du code — on ne peut pas écraser `main` sans review

## Décision

### Architecture : `cnp-ci-modules` + include minimal

Nous avons décidé d'héberger la logique CI dans un repo dédié `cnp-ci-modules` (actuellement `4k-cnp-2027/cnp-ci-modules` sur `gitlab.com`), et d'injecter dans chaque repo applicatif un `.gitlab-ci.yml` **minimal** qui délègue via le mécanisme `include: project:` de GitLab CI.

Le fichier injecté ne contient que des variables et des includes — toute la logique vit dans `cnp-ci-modules`. Cela permet de mettre à jour la baseline CI sans toucher aux repos applicatifs.

Structure de `cnp-ci-modules` :
```
base/
  pipeline.yml      ← baseline obligatoire (hadolint, gitleaks, trivy, docker-build, cnp-callback)
frameworks/
  python.yml        ← jobs spécifiques Python
  generic.yml       ← placeholder valide, aucun job supplémentaire
  ...
```

### Stratégie d'injection selon l'origin

- **scaffolded** → push direct sur `main` (le commit porte `[skip ci]` si l'option `skip_first_deploy` est activée au scaffold, sinon commit normal)
- **imported** → création d'une branche `cnp/inject-ci-{timestamp}` + MR vers `main`

### Détection de framework

Au moment de l'enregistrement, le backend inspecte l'arborescence racine du repo via l'API GitLab (bot token) et détecte :
- `python` si `requirements.txt`, `pyproject.toml`, `setup.py`, `setup.cfg` ou `Pipfile` est présent
- `generic` sinon

Le champ `Application.framework` est nullable : `null` déclenche la détection automatique, une valeur non-nulle est respectée (surcharge utilisateur via le portail).

### Workflow CI : pipeline MR uniquement

`base/pipeline.yml` définit un `workflow: rules` qui :
1. Fait tourner le pipeline MR (`merge_request_event`) quand une MR est ouverte
2. Supprime le pipeline de branche redondant quand une MR est ouverte (`when: never`)
3. Fait tourner un pipeline de branche normal si pas de MR (ex: push sur `main` après merge)

Ce choix évite les pipelines en double et fait tourner la CI sur le résultat simulé du merge — plus représentatif de ce qui atterrira sur `main`.

### Bot token

L'injection utilise un token dédié (`GITLAB_BOT_TOKEN`) distinct des tokens OAuth utilisateurs. Ce token a les droits `api` sur les repos CNP.

### Validation avant création en DB

Si `repo_url` est fourni à la création d'une app, CNP valide que le repo est accessible via le bot **avant** toute écriture en base. Une erreur 422 est retournée si le repo n'existe pas ou n'est pas accessible.

### Traçabilité : champ `ci_injected`

Le résultat de l'injection est exposé dans `ApplicationResponse.ci_injected` (bool nullable) :
- `true` → injection réussie
- `false` → injection échouée (app créée, CI non injectée)
- `null` → non applicable (pas de repo_url ou origin non concerné)

## Conséquences

Positif :
- Baseline de sécurité garantie sur tous les repos CNP sans intervention manuelle
- Mise à jour de la CI centralisée dans `cnp-ci-modules`, transparente pour les apps
- Détection de framework extensible (ajouter un fichier dans `frameworks/` suffit)
- Comportement CI cohérent entre les repos (un seul pipeline par événement)

Négatif / Dette :
- **Token PAT personnel** utilisé faute de Group Access Token sur `gitlab.com` free tier — à migrer vers un Group Access Token si upgrade vers Premium ou self-hosted (voir 4K-41)
- **Callback CNP** (`cnp-callback` job) non fonctionnel en local (CNP non accessible depuis les runners GitLab) — `allow_failure: true` posé en attendant le déploiement cloud
- **Authentification callback** manuelle pour la démo (variable `CNP_CALLBACK_TOKEN` à poser à la main) — automatisation prévue dans 4K-41
- L'endpoint `POST /api/v1/apps/{id}/ci-status` n'existe pas encore

Neutre :
- Le `.gitlab-ci.yml` injecté sur les repos scaffoldés est marqué `[skip ci]` si `skip_first_deploy=true`, sinon le commit est normal et la CI s'exécute immédiatement
- Si `.gitlab-ci.yml` existe déjà sur `main` d'un repo scaffoldé, l'injection est bloquée (`ci_injected: false`) — pas d'écrasement silencieux
