# Inventaire des dépendances (SBOM)

Page admin **Dependencies** : quand une CVE tombe, un admin CNP voit en quelques secondes **quelles apps utilisent la
dépendance concernée** (version, directe/transitive, licence). Complète l'onglet Security (« cette app a quelles
failles ? ») par la question inverse : « cette dépendance, ou cette CVE, touche quelles apps ? ».

## Flux

```
pipeline app (branche par défaut)
  trivy fs → sbom.json (CycloneDX) ─► job cnp-report ──POST gzip X-CNP-Token──► /api/v1/webhooks/ci-sbom
                                       (2e POST, après celui du rapport Security)   │ HMAC valide ? remplace les composants de l'app
Page admin /admin/dependencies ◄── GET /admin/dependencies, /admin/dependencies/by-cve
```

- **CI** (`cnp-ci-modules/security/cnp-report.yml`) : réduit `sbom.json` aux composants de type `library` :
  `purl`, `name`, `version`, `ecosystem` (type du purl), `direct`, `licenses`. Plafond 5000 composants
  (`truncated: true` au-delà). URL = `CNP_REPORT_URL` dont le dernier segment est remplacé par `ci-sbom`.
- **Compression** : `Content-Encoding: gzip` (le plus simple, aucune lib). Un JSON brut est aussi accepté.
- **Tolérance** : `sbom.json` absent/illisible, 404 (backend pas encore à jour), 5xx, réseau, timeout 10 s → une
  ligne de log, le job n'échoue pas à cause de l'inventaire et le POST Security n'en dépend pas.
- **`direct`** : `true` si le composant est dans le `dependsOn` du composant racine (en traversant le lockfile
  « application » que trivy place entre la racine et les librairies), `false` s'il est dans le graphe sans y être,
  `null` si le graphe est absent. Une lockfile sans relations (ex. `requirements.txt`) donne « direct » pour tout.

## Backend

| Élément | Détail |
|---|---|
| Tables | `sbom_snapshots` (1 ligne par app : `pipeline_id`, `commit_sha`, `received_at`, `component_count`, `truncated`) et `sbom_components` (`app_id` FK cascade, `name`, `version`, `ecosystem`, `purl`, `direct`, `licenses` JSON). Pas d'historique. Index `lower(name)`, `(ecosystem, name)` et `app_id`. Migration `f5a6b7c8d9e0`. |
| `POST /webhooks/ci-sbom` | Même token HMAC que le rapport Security (`HMAC-SHA256(SECRET_KEY, "ci-security-report:<app_id>")`, comparaison en temps constant). Un `pipeline_id` ≤ au stocké est ignoré (rejeu, ordre) ; sinon delete + insert en masse + snapshot **dans une transaction**. 200 `{stored}`, 401 token, 404 app, 413 trop gros, 422 invalide. |
| Bornes | 2 Mo sur le fil, 8 Mo décompressé (anti-bombe gzip), 5000 composants, chaînes ≤ 100–500 car., 10 licences. Champs inconnus ignorés. |
| `GET /admin/dependencies?q=&version=&ecosystem=&limit=&offset=` | Admin uniquement (403 sinon). `q` : contient, insensible à la casse, `%`/`_` littéraux ; `version`/`ecosystem` : égalité. `limit` ≤ 200. Réponse : lignes + `total` + `coverage` (`apps_total`, `apps_with_sbom`, snapshots le plus ancien/récent). |
| `GET /admin/dependencies/by-cve?id=CVE-…` | Admin uniquement. Voir ci-dessous. |

## Recherche par CVE (OSV.dev)

Ce qui a été vérifié dans la doc OSV : `GET https://api.osv.dev/v1/vulns/{id}` renvoie une vulnérabilité par
identifiant, et le champ `aliases` référence les mêmes failles dans d'autres bases (CVE, GHSA). Essai réel unique avec
`CVE-2021-44228` : HTTP 200, l'identifiant CVE est résolu directement, mais **cet enregistrement n'a que des plages
GIT, sans package ni écosystème** ; les packages (`Maven org.apache.logging.log4j:log4j-core`, liste `versions`
explicite, plage) sont dans l'alias GHSA. Le backend récupère donc la CVE **puis ses alias** (8 max) et fusionne les
`affected[]`. La récupération des alias n'a été validée que par les tests (httpx mocké) et le comportement documenté :
à confirmer sur l'API réelle après déploiement.

- Seuls des **identifiants de vulnérabilité** quittent la plateforme (GET sans corps ni paramètre, `User-Agent: cnp-backend`),
  jamais de donnée d'app (test dédié).
- Par package affecté (écosystèmes de l'inventaire : npm, PyPI, Go, Maven, crates.io, RubyGems), la correspondance
  se fait sur le **purl** (namespace Maven `groupId/artifactId`, nom PyPI normalisé, préfixe `v` des versions Go ignoré).
  Liste `versions` OSV explicite → égalité de version (« version affectée utilisée »). Plages seules → **non évaluées** :
  toutes les apps qui utilisent le package sont listées avec la plage en clair (« plage non évaluée automatiquement »).
  Pas de moteur de comparaison de versions.
- Timeout 5 s, erreurs OSV → 404 « inconnue d'OSV » ou 424 message lisible ; cache mémoire par process, TTL 10 min.
- Un alias illisible donne `partial: true` (la liste peut être incomplète), affiché dans l'UI.

## Limites (affichées dans l'UI)

- Le scan lit les **lockfiles du dépôt à la racine** (`trivy fs`), pas l'image réellement déployée.
- L'inventaire vient de la **branche par défaut**, pas forcément de ce qui tourne en prod.
- Une app sans pipeline récent est absente : le bandeau de couverture (« N apps sur M ont un inventaire ») évite de
  lire « aucun résultat » comme « personne n'est touché ».
- Pas de veille automatique : c'est l'admin qui cherche.
- Un composant listé plusieurs fois avec le même purl+version est dédoublonné ; au-delà de 5000, `truncated`.

## Exploitation

- **Ordre de déploiement** (inverse de l'onglet Security) : **backend d'abord** (route + migration), `cnp-ci-modules`
  ensuite. Si le module passe avant, le POST SBOM reçoit un 404 ignoré.
- Les apps existantes alimentent l'inventaire à leur prochain pipeline de branche par défaut (le job `cnp-report`
  et ses variables sont déjà injectés ; rien à ré-injecter).
- Le POST SBOM n'ajoute pas de minute de CI significative (même job).
