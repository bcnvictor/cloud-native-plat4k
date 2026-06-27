# ADR-0021 : Exposition HTTPS de Grafana via Let's Encrypt + nginx sur la VM OCI

## Statut

Accepted : 2026-06-27 — Implémentation complète. Grafana accessible sur `https://grafana.cloud-native-plat4k.me`. Voir ticket 4K-97.

## Contexte

Suite à ADR-0020, le Grafana central est déployé sur la VM OCI (`cnp-control`). Le besoin initial était d'exposer Grafana publiquement pour les opérateurs. Le ticket 4K-97 ajoute une contrainte nouvelle : les dashboards Grafana doivent être **embarqués en iframe** dans le frontend CNP (onglet "Métriques" de chaque groupe).

### Contrainte mixed-content

Un navigateur refuse de charger une iframe HTTP depuis une page HTTPS. Le frontend CNP est servi en HTTPS via Cloudflare. Grafana doit donc être en HTTPS pour être embeddable.

### Infrastructure existante

La VM OCI n'est pas gérée par Terraform (contrairement à l'AKS Azure). Il n'y a pas de cert-manager Kubernetes, pas de cloud load balancer avec terminaison TLS automatique. La VM expose les ports directement.

### Alternatives considérées

| Option | Raison d'écarter |
|---|---|
| **Cloudflare Flexible SSL** | TLS Cloudflare → navigateur, mais HTTP Cloudflare → VM. Grafana reste en HTTP côté serveur. Les iframes cross-origin voient l'URL finale (`grafana.cloud-native-plat4k.me`) qui serait HTTPS — fonctionnel en apparence, mais la connexion backend est non chiffrée. Carte grise : acceptable pour un usage interne limité mais pas propre. |
| **Cloudflare Tunnel** | Élimine le besoin d'ouvrir le port 443, mais ajoute un daemon Cloudflared sur la VM et une dépendance au réseau Cloudflare pour tout le trafic Grafana. Overkill pour un seul service. |
| **Caddy** | Gestion TLS automatique intégrée. Aurait simplifié la configuration. Écarté car nginx était déjà en place pour le frontend CNP, et ajouter un deuxième reverse proxy aurait complexifié l'opération. |
| **Cert-manager sur AKS** | Grafana est sur la VM OCI, pas dans le cluster AKS. Cette option ne s'applique pas. |

## Décision

Nous avons décidé d'exposer Grafana via **nginx en tant que reverse proxy TLS** sur la VM OCI, avec un certificat Let's Encrypt obtenu par **Certbot en challenge HTTP-01 (webroot)**.

### Architecture déployée

```
Navigateur
    │ HTTPS :443
    ▼
nginx-grafana (Docker, port 443)
    │ nginx lit le certificat Let's Encrypt
    │ proxy_pass HTTP :3000
    ▼
grafana (Docker, port 3000, non exposé)

Certbot (Docker, profil production)
    │ dépose /.well-known/acme-challenge/ dans un volume partagé
    ▼
frontend nginx (port 80)
    │ sert /.well-known/acme-challenge/ depuis le même volume
    ▼
Let's Encrypt (validation HTTP-01)
```

Le challenge HTTP-01 transite par le frontend nginx (déjà exposé sur :80). Le certbot et le nginx-grafana partagent deux volumes nommés : `letsencrypt` (certificats) et `certbot_webroot` (fichiers de challenge).

### Composants ajoutés à docker-compose.yml (profil `production`)

- **`nginx-grafana`** : nginx:alpine + template de config (`infra/grafana/nginx-grafana.conf.template`). L'entrypoint (`infra/grafana/docker-entrypoint-grafana-nginx.sh`) attend le certificat avant de démarrer, puis recharge nginx toutes les 6h pour prendre en compte les renouvellements.
- **`certbot`** : boucle de renouvellement (`certbot renew`) déclenchée toutes les 12h. Le premier certificat est obtenu via `infra/scripts/certbot-init.sh` (one-shot, exécuté manuellement au déploiement).

### DNS

Le domaine `grafana.cloud-native-plat4k.me` est géré sur Cloudflare. Le challenge HTTP-01 exige que Let's Encrypt puisse joindre directement la VM sur le port 80 — Cloudflare doit donc être en mode **DNS only** (nuage gris) sur cet enregistrement pendant l'émission. En mode proxy (nuage orange), Cloudflare intercepte le challenge et Let's Encrypt ne peut pas valider.

### Variables d'environnement

| Variable | Où | Rôle |
|---|---|---|
| `GRAFANA_DOMAIN` | `.env` VM OCI | Domaine DNS de Grafana (ex: `grafana.cloud-native-plat4k.me`) |
| `CERTBOT_EMAIL` | `.env` VM OCI | Email pour les notifications d'expiration Let's Encrypt |
| `GRAFANA_URL` | Vault `secret/cnp/platform` | URL publique Grafana, browser-accessible. Utilisée par le backend pour construire les URLs d'embed. |
| `GRAFANA_DASHBOARD_UID` | Vault `secret/cnp/platform` | UID du dashboard `cnp—group-overview` dans Grafana (visible dans l'URL `/d/{UID}/…`). |
| `GRAFANA_EMBED_TOKEN` | Vault `secret/cnp/platform` | Token d'un service account Grafana (rôle Viewer). Injecté dans les URLs d'iframe par le backend. Ne jamais exposer côté frontend. |

### Intégration frontend

Le frontend CNP (onglet "Métriques" de chaque groupe) appelle `GET /api/v1/groups/{id}/grafana-url` (endpoint authentifié CNP). Le backend retourne deux URLs avec le token d'embed baked-in :

```
panel_base_url  →  https://grafana.../d-solo/{uid}?orgId=1&auth_token=TOKEN&var-group_id={gid}
dashboard_url   →  https://grafana.../d/{uid}?orgId=1&auth_token=TOKEN&var-group_id={gid}
```

Le frontend ajoute `&panelId={id}&theme={light|dark}&refresh=30s` sur chaque iframe. Le token ne transite jamais dans le bundle JS — il est uniquement présent dans les réponses API (authentifiées) et dans les URLs d'iframe (visibles dans les devtools réseau, acceptable car read-only).

L'accès anonyme est désactivé (`GF_AUTH_ANONYMOUS_ENABLED=false`). Grafana n'est pas accessible sans token ou login admin.

## Conséquences

Positif :
- Grafana accessible en HTTPS avec certificat valide Let's Encrypt — pas de warning navigateur.
- Embedding en iframe fonctionnel sans erreur mixed-content.
- Renouvellement automatique via le service `certbot` en production.
- Aucun coût additionnel (Let's Encrypt est gratuit, nginx est déjà présent).

Négatif / Dette :
- Le challenge HTTP-01 impose que le port 80 de la VM soit accessible publiquement et que Cloudflare soit en DNS only sur `grafana.cloud-native-plat4k.me`. Un passage en proxy Cloudflare (orange) bloquerait les renouvellements.
- Si la VM OCI change d'IP publique, l'enregistrement DNS doit être mis à jour manuellement.
- Le premier certificat (`certbot-init.sh`) est une étape manuelle à rejouer en cas de recréation des volumes.
- `nginx-grafana` est un SPOF : si le container plante, Grafana n'est plus accessible. `restart: unless-stopped` en atténue l'impact.

Neutre :
- Grafana reste sur la VM OCI (pas dans le cluster Kubernetes). Cohérent avec ADR-0020.
- Le port 3000 de Grafana n'est pas exposé directement — uniquement accessible via nginx sur :443.
