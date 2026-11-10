# ADR-0028 : Authentification JWT des iframes Grafana

## Statut

Proposed : 2026-11-02

Remplace la partie « token de service account » de l'[ADR-0021](0021-grafana-https-letsencrypt.md).

## Contexte

Les iframes CNP passaient un token de service account dans le paramètre d'URL `auth_token`.
Grafana ne lit ce paramètre que pour un JWT, avec `url_login` activé : le token était donc
ignoré (`/api/org?auth_token=<token>` répond 401 en prod, alors que le même token passe en
`Authorization: Bearer`). Les panneaux ne s'affichaient que dans un navigateur ayant déjà une
session Grafana, et les autres utilisateurs tombaient sur la page de login.

## Décision

Le backend signe un JWT pour le user CNP qui demande les URLs d'embed (`/groups/{id}/grafana-url`,
`/admin/finops/grafana-urls`), et Grafana le vérifie avec `[auth.jwt]` et `url_login`.

- **Signature** : ES256. La clé privée reste dans Vault (`GRAFANA_JWT_PRIVATE_KEY`, PEM en
  base64), Grafana n'a que la clé publique (`GRAFANA_JWT_PUBLIC_KEY_B64` dans le `.env`).
- **Claims** : `sub = cnp-user-{id}`, `iss = cnp-backend`, `role = Viewer`. Le préfixe évite toute
  collision avec un compte Grafana existant, le rôle est toujours Viewer.
- **Comptes** : créés à la première connexion (`auto_sign_up`).
- **Durée de vie** : 8 h. Le frontend renouvelle les URLs toutes les 4 h, ou au retour sur l'onglet
  si elles ont plus de 4 h. Hors de ces moments, il ne les redemande pas : chaque token étant
  différent, cela rechargerait les iframes. Un token expiré envoie l'iframe sur la page de login
  (environ une minute après `exp`, d'après l'essai sur Grafana 13.1.0) ; une nouvelle URL la rétablit.
- **Sans clé configurée** : le JWT reste désactivé dans Grafana, et les routes renvoient des URLs
  vides (« Grafana not configured » dans l'UI). Le code peut donc être déployé avant les clés.

Le filtre `var-group_id` reste un simple paramètre d'URL : un utilisateur CNP peut voir les métriques
d'un autre groupe. C'est accepté, les groupes appartenant à la même organisation.

### Alternatives écartées

- **Accès anonyme Viewer** : expose métriques et coûts sur Internet.
- **Reverse proxy ajoutant l'en-tête** (`auth_request` nginx) : l'iframe devrait envoyer la
  session CNP à Grafana, or le frontend s'authentifie par token et non par cookie.
- **Graphiques natifs CNP** : la solution la plus propre si l'isolation entre groupes devient un
  besoin, mais un chantier nettement plus long.

## Conséquences

- Tout utilisateur CNP voit les panneaux, sans compte Grafana à gérer.
- Un token qui fuite (historique, logs) n'est valable que 8 h, contre un token permanent avant.
- Un token reste valide jusqu'à son expiration, même si le compte CNP est désactivé entre-temps.
- Le lien « View in Grafana » ouvre le dashboard avec le token de l'URL. Naviguer ailleurs dans
  Grafana renvoie au login, puisque le token n'est plus dans l'URL. Le compte admin reste
  nécessaire pour éditer.
- Le token de service account `GRAFANA_EMBED_TOKEN` n'est plus utilisé : à révoquer après l'activation.

## Mise en œuvre

Voir [Grafana : dashboards](../guides/grafana-dashboards.md) et `infra/grafana/setup-embed-jwt.sh`.
