# Test — CI Injector (4K-39)

## Prérequis

- Stack CNP démarrée (`./start.sh`)
- `.env` contient `GITLAB_BOT_TOKEN`, `GITLAB_BOT_NAMESPACE=victor.biancini`, `CNP_API_BASE_URL`
- Un repo de test vide créé sur GitLab : `https://gitlab.cri.epita.fr/victor.biancini/cnp-test`
- Le bot a accès en écriture à ce repo

---

## 0. Login

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -d 'username=admin@cnp.local&password=admin' \
  | jq -r '.access_token')
```

---

## 1. Vérifier la génération du template (sans GitLab)

```bash
docker-compose exec backend python -c "
from backend.ci.templates import generate_gitlab_ci
print(generate_gitlab_ci('mon-app', 42, 'python'))
"
```

Résultat attendu : un YAML avec `include: project: victor.biancini/cnp-ci-templates`.

---

## 2. Repo inexistant → doit fail avec 422

```bash
curl -s -X POST http://localhost:8000/api/v1/apps/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "repo-inexistant",
    "owner": "victor",
    "origin": "scaffolded",
    "repo_url": "https://gitlab.cri.epita.fr/victor.biancini/ce-repo-nexiste-pas"
  }' | jq .
```

Résultat attendu :
```json
{"detail": "GitLab repo not found or not accessible: https://..."}
```

---

## 3. Scaffolded → push direct sur main

```bash
curl -s -X POST http://localhost:8000/api/v1/apps/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "cnp-test",
    "owner": "victor",
    "origin": "scaffolded",
    "repo_url": "https://gitlab.cri.epita.fr/victor.biancini/cnp-test"
  }' | jq '{id, framework, ci_injected, status}'
```

Résultat attendu :
```json
{"id": ..., "framework": "generic", "ci_injected": true, "status": "onboarding"}
```

Vérifier sur GitLab que `.gitlab-ci.yml` est apparu sur `main`.

---

## 4. Scaffolded → CI déjà présente → doit fail proprement

Relancer la même commande qu'au test 3 (`.gitlab-ci.yml` existe déjà sur main).

Résultat attendu :
```json
{"id": ..., "framework": "generic", "ci_injected": false, "status": "onboarding"}
```

L'app est créée mais `ci_injected: false` signale que l'injection a été bloquée.

---

## 5. Imported → MR ouverte

Supprimer d'abord le `.gitlab-ci.yml` du repo de test (ou utiliser un autre repo vide), puis :

```bash
curl -s -X POST http://localhost:8000/api/v1/apps/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "cnp-test-imported",
    "owner": "victor",
    "origin": "imported",
    "repo_url": "https://gitlab.cri.epita.fr/victor.biancini/cnp-test"
  }' | jq '{id, framework, ci_injected, status}'
```

Résultat attendu :
```json
{"id": ..., "framework": "generic", "ci_injected": true, "status": "onboarding"}
```

Vérifier sur GitLab qu'une MR `cnp/inject-ci-YYYYMMDDHHMMSS → main` est ouverte.

---

## 6. Détection framework Python

Ajouter un `requirements.txt` à la racine du repo de test sur GitLab, puis créer une nouvelle app :

```bash
curl -s -X POST http://localhost:8000/api/v1/apps/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "cnp-test-python",
    "owner": "victor",
    "origin": "scaffolded",
    "repo_url": "https://gitlab.cri.epita.fr/victor.biancini/cnp-test"
  }' | jq '{id, framework, ci_injected}'
```

Résultat attendu : `"framework": "python"`.

---

## Nettoyage entre les tests

```bash
# Supprimer une app par son id
curl -s -X DELETE http://localhost:8000/api/v1/apps/{id} \
  -H "Authorization: Bearer $TOKEN"
```
