# Runbook Opérationnel : Intégration HashiCorp Vault

Ce runbook décrit la gestion de l'infrastructure HashiCorp Vault au sein de la plateforme CNP (Cloud Native Platform), tant pour le développement local que pour la production sur `cnp-control`.

---

## 💻 1. Développement Local (Zéro-Configuration)

Pour les développeurs de la plateforme (équipe de 6), le lancement local est transparent :

- **Lancement** : Exécutez simplement `./scripts/start.sh` (ou `docker compose up -d`).
- **Fonctionnement interne** :
  - Aucun conteneur Vault n'est démarré localement.
  - Le backend est configuré via `docker-compose.override.yml` pour se connecter directement au Vault de développement distant partagé (l'URL et le token y sont définis par défaut).
  - Au démarrage, le backend FastAPI récupère les configurations et secrets partagés directement depuis cette instance distante.
  - Les développeurs peuvent écraser les coordonnées du Vault dans leur `.env` local (`VAULT_ADDR` et `VAULT_TOKEN`) si nécessaire.

---

## 🚀 2. Déploiement en Production (`cnp-control`)

En production, Vault est configuré de manière sécurisée (mode serveur standard, stockage persistant persistant, et déverrouillage manuel by design).

### Étape 2.1 : Lancement sécurisé (sans les overrides de dev)

Le service Vault est déclaré sous le profile `production` dans `docker-compose.yml`. Pour le démarrer :

```bash
cd ~/cloud-native-plat4k
docker compose --profile production up -d vault
```

> **Note TLS** : Vault est configuré avec `tls_disable = true` (voir `vault.hcl`). Toutes les commandes `vault exec` doivent donc passer `VAULT_ADDR=http://127.0.0.1:8200` explicitement — sans quoi le CLI tente une connexion HTTPS et échoue.

### Étape 2.2 : Initialisation du coffre (première fois uniquement)

Lors du premier lancement de Vault sur la VM `cnp-control`, exécutez la commande d'initialisation :

```bash
docker compose exec -e VAULT_ADDR=http://127.0.0.1:8200 vault vault operator init -key-shares=5 -key-threshold=3
```

Cette commande génère :
1. **5 clés de déverrouillage (Unseal keys)**.
2. **1 Root Token**.

> [!WARNING]
> **Sauvegardez immédiatement ces informations en lieu sûr (gestionnaire de mots de passe d'équipe)**. Si vous perdez les clés de déverrouillage, l'accès à l'ensemble des secrets de la plateforme sera définitivement perdu.

### Étape 2.3 : Déverrouillage manuel (Unseal)

Après chaque redémarrage du conteneur Vault ou de la VM `cnp-control`, Vault démarre dans l'état **Sealed** (verrouillé) et refuse de servir les requêtes.

Pour le déverrouiller, exécutez 3 fois la commande suivante avec 3 des 5 clés d'unseal générées lors de l'initialisation :

```bash
docker compose exec -e VAULT_ADDR=http://127.0.0.1:8200 vault vault operator unseal <clé_1>
docker compose exec -e VAULT_ADDR=http://127.0.0.1:8200 vault vault operator unseal <clé_2>
docker compose exec -e VAULT_ADDR=http://127.0.0.1:8200 vault vault operator unseal <clé_3>
```

Une fois le seuil de 3 clés atteint, la sortie affichera `Sealed: false`.

Vérification :
```bash
docker compose exec -e VAULT_ADDR=http://127.0.0.1:8200 vault vault status
```

Puis relancer le backend (qui a échoué à démarrer en attendant Vault) :
```bash
docker compose up -d
```

### Étape 2.4 : Configuration initiale de la production

Une fois Vault unsealed, connectez-vous avec le Root Token :

```bash
docker compose exec -e VAULT_ADDR=http://127.0.0.1:8200 -e VAULT_TOKEN=<root_token> vault vault status
```

1. **Activer le moteur KV v2** :
   ```bash
   docker compose exec -e VAULT_ADDR=http://127.0.0.1:8200 -e VAULT_TOKEN=<root_token> vault vault secrets enable -path=secret kv-v2
   ```

2. **Créer la policy pour le backend** :

   Selon le mode de bootstrapping choisi, deux policies sont disponibles :

   **Option A — Bootstrapping automatique (recommandé pour la simplicité)** : le backend s'auto-configure en production au premier démarrage. Le token applicatif doit pouvoir écrire dans `cnp/*` **uniquement lors du premier boot**, puis la policy peut être resserrée ensuite.

   Créez un fichier local temporaire `cnp-backend-policy.hcl` contenant :
   ```hcl
   # Lecture des secrets de la plateforme (settings, clés)
   path "secret/data/cnp/*" {
     capabilities = ["read", "create", "update"]
   }

   # Gestion complète des kubeconfigs de clusters
   path "secret/data/clusters/*" {
     capabilities = ["read", "create", "update", "delete"]
   }

   path "secret/delete/clusters/*" {
     capabilities = ["update"]
   }

   path "secret/metadata/clusters/*" {
     capabilities = ["delete"]
   }
   ```

   **Option B — Bootstrapping manuel (plus sécurisé)** : vous initialisez `secret/cnp/platform` vous-même avec le Root Token (voir étape 2.5b), et le token applicatif n'a que `read` sur `cnp/*`.

   ```hcl
   # Lecture seule des secrets de la plateforme
   path "secret/data/cnp/*" {
     capabilities = ["read"]
   }

   # Gestion complète des kubeconfigs de clusters
   path "secret/data/clusters/*" {
     capabilities = ["read", "create", "update", "delete"]
   }

   path "secret/delete/clusters/*" {
     capabilities = ["update"]
   }

   path "secret/metadata/clusters/*" {
     capabilities = ["delete"]
   }
   ```

   > [!IMPORTANT]
   > Si vous choisissez l'Option B, vous **devez** pré-remplir `secret/cnp/platform` avec le Root Token **avant** de démarrer le backend (voir étape 2.5b). Sans cela, le backend s'arrêtera avec une erreur `Vault Forbidden on write`.

   Enregistrez la policy directement dans Vault (inline, sans fichier temporaire) :
   ```bash
   docker compose exec -e VAULT_ADDR=http://127.0.0.1:8200 -e VAULT_TOKEN=<root_token> vault \
     vault policy write cnp-backend - << 'EOF'
   path "secret/data/cnp/*" {
     capabilities = ["read", "create", "update"]
   }
   path "secret/data/clusters/*" {
     capabilities = ["read", "create", "update", "delete"]
   }
   path "secret/delete/clusters/*" {
     capabilities = ["update"]
   }
   path "secret/metadata/clusters/*" {
     capabilities = ["delete"]
   }
   EOF
   ```

3. **Générer le token applicatif pour le backend** :
   ```bash
   docker compose exec -e VAULT_ADDR=http://127.0.0.1:8200 -e VAULT_TOKEN=<root_token> vault \
     vault token create -policy=cnp-backend -period=720h -format=json
   ```
   Copiez le `client_token` retourné (`hvs.xxxxxxxx...`).

4. **Injecter le token dans le `.env` de production et redémarrer** :
   ```bash
   sed -i "s|^VAULT_TOKEN=.*|VAULT_TOKEN=hvs.le_token_applicatif|" .env
   docker compose up -d
   ```

   > **Important** : le Root Token ne doit plus être utilisé après cette étape. Conservez-le uniquement dans votre gestionnaire de mots de passe d'équipe pour les opérations d'administration Vault (rotation des secrets, création de nouvelles policies).

### Étape 2.5 : Lancement du Backend

#### 2.5a — Avec bootstrapping automatique (Option A)

Une fois Vault opérationnel, initialisé, unsealed, et le token configuré dans le `.env` de production :

```bash
docker compose -f docker-compose.yml up -d backend db frontend
```

Au premier démarrage, le backend détectera que le chemin `secret/cnp/platform` est vierge et y poussera automatiquement les valeurs de `SECRET_KEY` et `POSTGRES_PASSWORD` de votre fichier `.env` de production.

Une fois cette étape validée, vous pouvez supprimer (ou laisser en guise de documentation) les variables `SECRET_KEY` et `POSTGRES_PASSWORD` du fichier `.env` de production : le backend les lira dorénavant directement depuis Vault.

#### 2.5b — Avec bootstrapping manuel (Option B)

Si vous avez choisi la policy en lecture seule sur `cnp/*`, pré-remplissez les secrets **avant** de démarrer le backend avec le Root Token :

```bash
docker compose exec -it vault vault login
# Entrer le Root Token

docker compose exec vault vault kv put secret/cnp/platform \
  SECRET_KEY="VotreCleSecreteDePlusDe32Caracteres" \
  POSTGRES_SERVER="db" \
  POSTGRES_USER="${POSTGRES_USER}" \
  POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
  POSTGRES_DB="${POSTGRES_DB}"
```

Puis démarrez le backend :

```bash
docker compose -f docker-compose.yml up -d backend db frontend
```

---

---

## Etat actuel sur `cnp-control` (référence)

> Mis à jour le 2026-06-25. Ce qui a été fait en production sur la VM Oracle.

| Étape | Statut | Notes |
|---|---|---|
| Service Vault démarré (`--profile production`) | OK | `docker compose --profile production up -d vault` |
| Vault initialisé (5 shares / threshold 3) | OK | Clés stockées dans le gestionnaire de mots de passe |
| Vault unsealed | OK | À refaire après chaque reboot (voir procédure post-reboot) |
| KV v2 activé sur `secret/` | OK | `vault secrets enable -path=secret kv-v2` |
| `secret/cnp/platform` bootstrappé | OK | Bootstrap automatique au premier démarrage backend |
| Policy `cnp-backend` créée | OK | Accès `read/create/update` sur `cnp/*`, `clusters/*` et `argocd/*` |
| Policy `cnp-backend` étendue à `apps/*` (4K-106) | À faire | Voir section 4 — requis pour que `PUT /api/v1/apps/{id}/env/{env}` fonctionne |
| Token applicatif en place | OK | Root token **non utilisé** par le backend |
| `.env` nettoyé | OK | Seuls `POSTGRES_*`, `VAULT_ADDR`, `VAULT_TOKEN`, `COMPOSE_FILE` |

---

## 🔑 3. Enregistrer le token ArgoCD pour un cluster

Cette procédure est à effectuer une fois par cluster, sur `cnp-control`. Elle stocke le Bearer token ArgoCD dans Vault via l'API CNP, ce qui permet au backend de contacter ArgoCD pour les statuts de sync/health.

### Prérequis

- Vault unsealed et le backend en cours d'exécution
- Tailscale actif sur `cnp-control` avec les routes acceptées (`sudo tailscale up --accept-routes`)
- `kubectl` configuré sur le cluster cible (kubeconfig disponible)

### Étape 3.1 — Vérifier la connectivité ArgoCD via Tailscale

Le subnet router Tailscale (`aks-subnet-router`) expose le CIDR du cluster (`10.0.0.0/16`). ArgoCD tourne comme service ClusterIP — il n'est pas accessible directement depuis le VNet, mais via Tailscale.

```bash
# Vérifier que le subnet router est visible
tailscale status | grep aks-subnet-router

# Vérifier que les routes sont dans la table Tailscale (table 52)
ip route show table 52 | grep 10.0

# Tester la connectivité ArgoCD
curl -k -s "https://<ARGOCD_CLUSTER_IP>/api/version" | jq .
# → doit retourner {"Version": "v3.x.x"}
```

**Erreurs fréquentes :**

| Erreur | Cause | Fix |
|--------|-------|-----|
| Timeout / connexion refusée | Routes subnet non acceptées localement | `sudo tailscale up --accept-routes` |
| Routes absentes de `ip route show table 52` | Daemon tailscaled redémarré sans le flag | Idem ci-dessus — le flag ne persiste pas automatiquement |
| `Not Found` sur `/api/v1/version` | Mauvais path — l'endpoint version ArgoCD est `/api/version` (sans `v1`) | Corriger l'URL |

> **Note réseau :** `cnp-control` est sur Oracle Cloud (`10.0.0.0/24`) et le cluster AKS est sur Azure — deux réseaux sans lien direct. Le seul pont est Tailscale. La route `10.0.0.0/16` est installée dans la table de routage 52 par Tailscale et prend priorité sur la table principale pour les adresses hors du `/24` Oracle (ex. `10.0.54.x` pour les ClusterIPs AKS).

### Étape 3.2 — Obtenir le token ArgoCD

**Récupérer le mot de passe admin ArgoCD depuis K8s :**
```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d && echo
```

**Obtenir un session token (valide 24h) :**
```bash
curl -k -s -X POST "https://<ARGOCD_IP>/api/v1/session" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<PASSWORD>"}' | jq -r .token
# → eyJhbGci...
```

**Générer un token long-lived (recommandé pour le backend) :**
```bash
# Le Bearer ici est le session token eyJhbGci... obtenu ci-dessus, PAS le mot de passe
curl -k -s -X POST "https://<ARGOCD_IP>/api/v1/account/admin/token" \
  -H "Authorization: Bearer <SESSION_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"expiresIn": 0, "id": "cnp-backend"}' | jq -r .token
# → eyJhbGci... (token sans expiration)
```

**Erreur fréquente :**

| Erreur | Cause |
|--------|-------|
| `{"error":"no session information"}` | Le champ `Authorization: Bearer` contient le mot de passe en clair au lieu du JWT session token |

### Étape 3.3 — Vérifier la policy Vault

La policy `cnp-backend` doit inclure les paths `argocd/*`. Vérifier :

```bash
docker exec -i <VAULT_CONTAINER_ID> \
  env VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=<ROOT_TOKEN> \
  vault policy read cnp-backend
```

La policy complète attendue (ajouter les blocs `argocd` si absents) :

```bash
docker exec -i <VAULT_CONTAINER_ID> \
  env VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=<ROOT_TOKEN> \
  vault policy write cnp-backend - << 'EOF'
path "secret/data/cnp/*" {
  capabilities = ["read", "create", "update"]
}
path "secret/data/clusters/*" {
  capabilities = ["read", "create", "update", "delete"]
}
path "secret/delete/clusters/*" {
  capabilities = ["update"]
}
path "secret/metadata/clusters/*" {
  capabilities = ["delete"]
}
path "secret/data/argocd/*" {
  capabilities = ["read", "create", "update", "delete"]
}
path "secret/metadata/argocd/*" {
  capabilities = ["delete"]
}
EOF
```

> **Pourquoi ce chemin ?** Le backend écrit dans Vault à `secret/data/argocd/{cluster_id}` (KV v2). Sans les paths `argocd/*` dans la policy, le write échoue silencieusement (loggé en ERROR, mais la réponse API est quand même 200).

**Trouver l'ID du container Vault :**
```bash
docker ps -f name=vault --format "{{.ID}} {{.Image}}"
# Prendre l'ID du container hashicorp/vault (pas un autre container dont le nom contient "vault")
```

**Erreur fréquente :**

| Erreur | Cause | Fix |
|--------|-------|-----|
| `cannot attach stdin to TTY-enabled container` | Flag `-it` incompatible avec heredoc | Remplacer `-it` par `-i` |
| `http: server gave HTTP response to HTTPS client` | `VAULT_ADDR` non passé, le CLI tente HTTPS | Toujours passer `VAULT_ADDR=http://127.0.0.1:8200` |
| `permission denied` sur `vault policy list` | Token sans droits admin | Utiliser le Root Token |

### Étape 3.4 — Enregistrer via l'API CNP

Le token ArgoCD ne doit **jamais** être écrit directement dans Vault. Passer par l'API CNP qui valide le payload, met à jour la DB (`ClusterConnection.argocd_url`) et écrit dans Vault (`secret/argocd/{cluster_id}`) de manière atomique.

```bash
# 1. S'authentifier au backend CNP
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -d "username=<EMAIL>&password=<PASSWORD>" | jq -r .access_token)

# 2. Enregistrer l'URL ArgoCD et le token
curl -s -X PUT http://localhost:8000/api/v1/clusters/<CLUSTER_ID> \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "argocd_url": "https://<ARGOCD_IP>",
    "argocd_token": "<LONG_LIVED_TOKEN>"
  }' | jq .
# → La réponse doit inclure "argocd_url": "https://..."
```

**Vérifier que le write Vault a bien eu lieu** dans les logs backend :
```bash
docker compose logs backend --tail=20
# Si la policy était incorrecte : "Failed to write secret to secret/argocd/1: permission denied"
# Si succès : pas d'erreur (le write est silencieux en cas de succès)
```

**Erreur fréquente :**

| Erreur | Cause | Fix |
|--------|-------|-----|
| `"detail": "Could not validate credentials"` | Le Bearer passé à l'API CNP est un JWT ArgoCD au lieu d'un JWT CNP | Se connecter via `/api/v1/auth/login` pour obtenir un token CNP |
| `401 Unauthorized` dans les logs backend | Même cause — token ArgoCD utilisé à la place du token CNP | Idem |
| Réponse 200 mais rien dans Vault | Policy manquante sur `argocd/*` — erreur loggée silencieusement | Voir étape 3.3 |

### État ArgoCD — référence cluster 1

| Élément | Valeur |
|---------|--------|
| ArgoCD ClusterIP | `10.0.54.71` (accessible via Tailscale subnet router) |
| URL enregistrée | `https://10.0.54.71` |
| Token Vault path | `secret/argocd/1` |
| Token type | API token long-lived (`expiresIn: 0`, id `cnp-backend`) |
| Policy Vault | `cnp-backend` avec paths `argocd/*` |

---

## 🔐 4. Étendre la policy `cnp-backend` pour les variables d'environnement (4K-106)

Le backend a besoin de lire/écrire/supprimer sous `secret/apps/*` pour la gestion des
variables d'environnement applicatives (ADR-0025). C'est distinct de la policy `eso-reader`
(`infra/eso/policy-eso-reader.hcl`, 4K-105) : `eso-reader` est **read-only**, réservée à
External Secrets Operator. `cnp-backend` a besoin d'écriture pour que
`PUT /api/v1/apps/{id}/env/{env}` et le cleanup Vault de `DELETE /api/v1/apps/{id}` fonctionnent.

Vérifier la policy actuelle :

```bash
docker exec -i <VAULT_CONTAINER_ID> \
  env VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=<ROOT_TOKEN> \
  vault policy read cnp-backend
```

Policy complète attendue (ajouter les blocs `apps` si absents, sans supprimer les blocs
`cnp`/`clusters`/`argocd` existants) :

```bash
docker exec -i <VAULT_CONTAINER_ID> \
  env VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=<ROOT_TOKEN> \
  vault policy write cnp-backend - << 'EOF'
path "secret/data/cnp/*" {
  capabilities = ["read", "create", "update"]
}
path "secret/data/clusters/*" {
  capabilities = ["read", "create", "update", "delete"]
}
path "secret/delete/clusters/*" {
  capabilities = ["update"]
}
path "secret/metadata/clusters/*" {
  capabilities = ["delete"]
}
path "secret/data/argocd/*" {
  capabilities = ["read", "create", "update", "delete"]
}
path "secret/metadata/argocd/*" {
  capabilities = ["delete"]
}
path "secret/data/apps/*" {
  capabilities = ["read", "create", "update", "delete"]
}
path "secret/metadata/apps/*" {
  capabilities = ["read", "list", "delete"]
}
EOF
```

> **Pourquoi ces deux blocs ?** `patch_secret`/`get_secret` (KV v2) passent par
> `secret/data/apps/*`. La suppression complète d'un env à la désinscription d'une app
> (`DELETE /api/v1/apps/{id}`, `vault_client.delete_secret`) appelle
> `delete_metadata_and_all_versions`, qui a besoin de `delete` sur `secret/metadata/apps/*`.
> Sans ce dernier bloc, le cleanup échoue silencieusement (loggé en ERROR, mais l'app est
> quand même supprimée de la DB) et des secrets orphelins restent dans Vault.

Sans cette extension, `PUT /api/v1/apps/{id}/env/{env}` répond 500 (`Vault Forbidden on
write`) et `DELETE /api/v1/apps/{id}` supprime l'app en base sans nettoyer Vault.

---

## 🛠️ 5. Dépannage et Administration Générale

### Procédure post-reboot (cnp-control)

Après tout redémarrage de la VM, Vault repart **Sealed**. Le backend ne peut pas démarrer tant que Vault n'est pas unsealed.

```bash
cd ~/cloud-native-plat4k

# Unsealer (3 clés sur 5)
docker compose exec -e VAULT_ADDR=http://127.0.0.1:8200 vault vault operator unseal <clé_1>
docker compose exec -e VAULT_ADDR=http://127.0.0.1:8200 vault vault operator unseal <clé_2>
docker compose exec -e VAULT_ADDR=http://127.0.0.1:8200 vault vault operator unseal <clé_3>

# Vérifier (Sealed: false)
docker compose exec -e VAULT_ADDR=http://127.0.0.1:8200 vault vault status

# Relancer le backend
docker compose up -d
```

### Vérifier le statut de Vault

```bash
docker compose exec -e VAULT_ADDR=http://127.0.0.1:8200 vault vault status
```

### Rotation des Secrets de la Plateforme

Pour modifier ou renouveler un secret dans Vault :
```bash
docker compose exec -e VAULT_ADDR=http://127.0.0.1:8200 -e VAULT_TOKEN=<root_token> vault \
  vault kv put secret/cnp/platform \
  SECRET_KEY="NouvelleCleSuperSecreteDePlusDe32Caracteres" \
  POSTGRES_PASSWORD="NouveauMotDePasseDB"
```

Redémarrez le backend pour charger la nouvelle configuration :
```bash
docker compose restart backend
```
