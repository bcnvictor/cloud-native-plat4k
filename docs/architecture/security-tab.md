# Onglet Security et correction en un clic

Chaque app a un onglet **Security** : résultats du dernier pipeline GitLab de la branche par défaut (CVE trivy,
secrets gitleaks), note A→F et bouton **Corriger** par finding. GitLab Free n'ayant pas l'UI Security (Ultimate),
le pipeline envoie lui-même un résumé réduit à CNP.

## Flux

```
pipeline app (branche par défaut)
  trivy (JSON) + gitleaks (JSON) ──► job cnp-report ──POST X-CNP-Token──► /api/v1/webhooks/ci-security-report
                                                                           │ HMAC valide ? upsert security_reports
Onglet Security ◄── GET /apps/{id}/security/latest (rapport + grade) ◄─────┘
```

- Table `security_reports` : **une ligne par app**, upsert à chaque rapport ; un `pipeline_id` plus ancien ou
  identique à celui stocké est ignoré (ordre + rejeu). Pas d'historique.
- **Token** : `HMAC-SHA256(SECRET_KEY, "ci-security-report:<app_id>")`, recalculé et comparé en temps constant,
  rien en base. Posé sur l'app en variable CI masquée `CNP_REPORT_TOKEN` à l'injection de la CI.
- **URL** : `CNP_CI_CALLBACK_URL` (env backend) sinon `CNP_API_BASE_URL` + `/api/v1/webhooks/ci-security-report`.
  Elle doit être joignable depuis les runners gitlab.com (à vérifier selon l'exposition de cnp-control).
- Le secret détecté par gitleaks ne quitte jamais le pipeline (règle, fichier, ligne uniquement) ; le backend ignore
  de toute façon les champs inconnus.
- Chaque scanner a un statut `ok` / `failed` / `skipped` : un scanner planté n'est jamais présenté comme « 0 finding ».

## Note (calculée à la lecture)

| Note | Condition |
|---|---|
| F | un secret détecté **ou** au moins une CVE CRITICAL |
| D | 5 HIGH ou plus |
| C | 1 à 4 HIGH |
| B | au moins une MEDIUM |
| A | sinon (aucune, ou seulement LOW/UNKNOWN) |

A et B exigent que **les deux** scanners aient abouti ; sinon aucune note (`null`, « partielle ») : un scanner planté
ne doit pas ressembler à un résultat propre. Un mauvais résultat (C, D, F) reste affiché même si l'autre scanner a échoué.

## API

| Route | Droit | Rôle |
|---|---|---|
| `POST /webhooks/ci-security-report` | token HMAC | ingestion (200 `{stored}`, 401 token invalide, 404 app inconnue) |
| `GET /apps/{id}/security/latest` | viewer | `{report, grade, partial}` (`report: null` si aucun scan) |
| `GET /apps/{id}/security/fix-prompt?finding=<id\|all>` | viewer | prompt Mode A (indépendant de l'IA) |
| `POST /apps/{id}/security/findings/{id}/autofix` | developer | Mode B, voir ci-dessous |

## Deux modes de correction

**Mode A — en local (recommandé).** CNP génère, par gabarits 100 % déterministes (aucun LLM), un prompt à coller
dans l'agent de code de l'utilisateur à la racine du dépôt cloné : contexte, finding, version corrigée, tâche
(correction minimale, tests et lint, branche, MR, ne pas toucher `.gitlab-ci.yml`), critère de succès, prudence.
Pour un secret, le prompt avertit en tête que **le secret est compromis dans l'historique git et doit être révoqué**
et ne contient jamais la valeur. Le texte passe par `ai/redaction.py` ; les longues listes sont tronquées.

**Mode B — avec l'IA de la CNP.** Périmètre étroit : CVE de dépendances trivy avec `FixedVersion` et un manifeste
connu (`requirements*.txt`, `pyproject.toml`, `package.json`, `go.mod`, `Pipfile` ; un lockfile trivy est ramené à
son manifeste et la MR précise qu'il reste à régénérer). Synchrone (timeout global 45 s), **un seul appel LLM**,
aucun état persistant :

1. IA activée (réglage existant) et app autorisée, rôle `developer` minimum ;
2. anti-doublon : la branche `cnp/autofix/<finding-id>` existe → URL de sa MR ;
3. lecture du seul manifeste cible (redacté avant envoi au modèle) ;
4. sortie JSON stricte `{"new_content": "..."}` ;
5. validation : seules des lignes de version du package visé changent (≤ 10 lignes), la version corrigée apparaît,
   chemin sur liste blanche, jamais `.gitlab-ci.yml`/`.git*` ; sinon réponse `no_fix` avec la raison ;
6. branche + commit unique + **MR en brouillon** (`Draft:`, label `cnp-autofix`) avec le bot GitLab ; une ligne d'audit
   `SECURITY_AUTOFIX_MR`. **Jamais de merge automatique.**

Limites : moins performant qu'un agent local, ne lance pas les tests, soumis aux quotas du provider (429 « Quota IA
atteint »), extraits de manifeste potentiellement envoyés à un fournisseur tiers. Le contenu du dépôt est une entrée
non fiable : seul un contenu validé est écrit.

## Exploitation

- **Ordre de déploiement** : merger d'abord `cnp-ci-modules` (fournit `security/cnp-report.yml`), puis le backend. Les `.gitlab-ci.yml` générés pour les nouvelles apps incluent ce fichier ; s'il manque, leur pipeline échoue.

- Rollout : les apps existantes doivent voir leur CI ré-injectée pour recevoir `cnp-report`, `CNP_REPORT_URL` et
  `CNP_REPORT_TOKEN`.
- Le bot GitLab (`GITLAB_BOT_TOKEN`) doit pouvoir créer branches et MR (et poser des variables CI) sur les apps.
- Le job `cnp-report` consomme environ une minute de CI par pipeline de branche par défaut (quota Free : 400 min).
