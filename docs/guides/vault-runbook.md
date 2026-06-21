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

Pour s'assurer que les configurations et services de développement (comme pgAdmin ou le mode dev de Vault) ne soient pas déployés en production, lancez explicitement Docker Compose en ciblant uniquement le fichier de configuration de base :

```bash
docker compose -f docker-compose.yml up -d vault
```

### Étape 2.2 : Initialisation du coffre (première fois uniquement)

Lors du premier lancement de Vault sur la VM `cnp-control`, exécutez la commande d'initialisation :

```bash
docker compose exec vault vault operator init -key-shares=5 -key-threshold=3
```

Cette commande génère :
1. **5 clés de déverrouillage (Unseal keys)**.
2. **1 Root Token**.

> [!WARNING]
> **Sauvegardez immédiatement ces informations en lieu sûr (gestionnaire de mots de passe d'équipe)**. Si vous perdez les clés de déverrouillage, l'accès à l'ensemble des secrets de la plateforme sera définitivement perdu.

### Étape 2.3 : Déverrouillage manuel (Unseal)

Après chaque redémarrage du conteneur Vault ou de la VM `cnp-control`, Vault démarre dans l'état **Sealed** (verrouillé) et refuse de servir les requêtes.

Pour le déverrouiller, 3 personnes différentes (ou l'administrateur détenant les clés) doivent exécuter la commande suivante avec 3 des 5 clés d'unseal générées lors de l'initialisation :

```bash
docker compose exec -it vault vault operator unseal
# Saisir la clé 1

docker compose exec -it vault vault operator unseal
# Saisir la clé 2

docker compose exec -it vault vault operator unseal
# Saisir la clé 3
```

Une fois le seuil de 3 clés atteint, la sortie affichera `Sealed: false`.

### Étape 2.4 : Configuration initiale de la production

Une fois Vault unsealed, connectez-vous avec le Root Token :

```bash
docker compose exec -it vault vault login
# Entrer le Root Token de production
```

1. **Activer le moteur KV v2** :
   ```bash
   docker compose exec vault vault secrets enable -path=secret kv-v2
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

   Enregistrez la policy dans Vault :
   ```bash
   docker compose exec -T vault vault policy write cnp-backend - < cnp-backend-policy.hcl
   rm cnp-backend-policy.hcl
   ```

3. **Générer le token applicatif pour le backend** :
   Générez un token renouvelable associé à la policy `cnp-backend` :
   ```bash
   docker compose exec vault vault token create -policy=cnp-backend -period=720h
   ```
   Copiez le token généré de type `hvs.xxxxxxxx...`.

4. **Injecter le token dans l'environnement de production** :
   Sur `cnp-control`, éditez le fichier `.env` de production :
   ```env
   VAULT_TOKEN=hvs.le_token_applicatif_genere
   ```

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

## 🛠️ 3. Dépannage et Administration

### Vérifier le statut de Vault

Pour vérifier si Vault est opérationnel et s'il est sealed :
```bash
docker compose exec vault vault status
```

### Rotation des Secrets de la Plateforme

Pour modifier ou renouveler la `SECRET_KEY` ou le mot de passe de base de données dans Vault :
```bash
# Se connecter avec le Root Token
docker compose exec -it vault vault login

# Mettre à jour le secret
docker compose exec vault vault kv put secret/cnp/platform \
  SECRET_KEY="NouvelleCleSuperSecreteDePlusDe32Caracteres" \
  POSTGRES_PASSWORD="NouveauMotDePasseDB"
```

Redémarrez le backend pour charger la nouvelle configuration :
```bash
docker compose -f docker-compose.yml restart backend
```
