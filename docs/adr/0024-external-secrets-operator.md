# ADR-0024 : External Secrets Operator (ESO) comme pont Vault → Kubernetes

## Statut

Accepted : 2026-07-03

## Contexte

La plateforme CNP gère déjà les secrets d'infrastructure dans HashiCorp Vault (ADR-0016) :
secrets internes sous `secret/cnp/platform`, kubeconfigs sous `secret/clusters/{id}`. Ces
secrets sont consommés par le backend CNP uniquement, via un token applicatif restreint.

Avec l'introduction de la gestion des variables d'environnement applicatives (ADR-0025),
les secrets des apps sont stockés dans Vault sous `secret/apps/{group_slug}/{app_slug}/{env}`.
Ces secrets doivent être injectés dans les pods Kubernetes au moment du déploiement, et
rester synchronisés en continu si une valeur est modifiée entre deux déploiements.

Deux mécanismes d'injection ont été évalués :

**Option A — Injection kubectl par le backend CNP** : le backend lit le secret dans Vault
et crée ou met à jour le `Secret` Kubernetes correspondant via l'API K8s, au moment du
déploiement. Simple à implémenter, mais la synchronisation est one-shot : une modification
ultérieure du secret dans Vault n'est pas répercutée dans le cluster sans redéploiement.
Le backend CNP joue le rôle de proxy secrets au-delà de son périmètre normal.

**Option B — External Secrets Operator (ESO)** : un opérateur Kubernetes (external-secrets.io)
tourne dans chaque cluster, déclare un `SecretStore` pointant vers Vault, et réconcilie
en continu les `ExternalSecret` CRDs vers des `Secret` Kubernetes natifs. Le backend CNP
ne manipule jamais les `Secret` K8s directement : il écrit dans Vault, ESO propage.

## Décision

Nous avons décidé d'adopter **External Secrets Operator** (option B) comme mécanisme de
synchronisation Vault → Kubernetes pour les secrets applicatifs.

### 1. Installation dans chaque cluster

ESO est installé via son chart Helm officiel dans un namespace dédié `external-secrets` :

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets \
  -n external-secrets --create-namespace
```

L'installation est répliquée sur AKS et sur le cluster k3s Oracle (`cnp-k3s`). Les
ressources consommées sont négligeables (~50-80 MB RAM, CPU idle quasi nul) — compatibles
avec les contraintes des deux clusters.

### 2. Authentification ESO → Vault via AppRole

ESO s'authentifie à Vault via AppRole (prévu en S2, ADR-0016). Un rôle AppRole dédié par
cluster est créé avec une policy restreinte en lecture sur `secret/apps/*` uniquement. Les
credentials AppRole (`role_id` + `secret_id`) sont stockés dans un `Secret` Kubernetes
bootstrappé manuellement lors de l'installation du cluster.

Pendant la période transitoire avant AppRole, un token statique à durée de vie longue est
utilisé, stocké dans le même `Secret` K8s. Ce token est remplacé par AppRole dès que la
migration AppRole est effectuée.

Un `ClusterSecretStore` (scope cluster-wide) est déclaré pour chaque cluster, pointant vers
le Vault sur `cnp-control` via Tailscale :

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: vault-backend
spec:
  provider:
    vault:
      server: "http://cnp-control:8200"
      path: "secret"
      version: "v2"
      auth:
        appRole:
          path: "approle"
          roleId: "<role_id>"
          secretRef:
            name: vault-approle-credentials
            namespace: external-secrets
            key: secret_id
```

### 3. Provisioning des ExternalSecrets par le backend CNP

Lors du provisioning GitOps d'une app (job `update-gitops`, ADR-0014), le backend génère
un manifest `ExternalSecret` par environnement dans `cnp-gitops` :

```
cnp-gitops/
  apps/{app_slug}/
    externalsecret-dev.yaml
    externalsecret-prod.yaml
    values-dev.yaml
    values-prod.yaml
```

Structure du manifest généré :

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: {app_slug}-env
  namespace: {app_namespace}
spec:
  refreshInterval: 5m
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: {app_slug}-env
    creationPolicy: Owner
  dataFrom:
    - extract:
        key: secret/apps/{group_slug}/{app_slug}/{env}
```

La directive `dataFrom.extract` synchronise l'intégralité des clés du secret Vault vers
un `Secret` Kubernetes de même nom. Le Helm chart de l'app référence ce secret via
`envFrom` dans le `Deployment` :

```yaml
envFrom:
  - secretRef:
      name: {app_slug}-env
```

Le `refreshInterval: 5m` garantit qu'une modification de secret dans Vault est propagée
dans le pod sous 5 minutes, sans redéploiement. Un redémarrage du pod est nécessaire pour
que les nouvelles valeurs soient lues par le process ; cela est géré par
**Stakater Reloader**, installé conjointement avec ESO, qui surveille les `Secret` K8s et
redémarre automatiquement les `Deployment` concernés lors d'un changement.

### 4. Cycle de vie si le chemin Vault est vide

Si aucune variable n'a encore été définie pour une app (`secret/apps/{group}/{app}/{env}`
n'existe pas dans Vault), l'`ExternalSecret` reste en état `SecretSyncedError`. Le pod
démarre sans le `secretRef` manquant uniquement si le Helm chart déclare `envFrom` comme
optionnel (`optional: true`). Le template Helm scaffoldé par CNP inclut cette directive
par défaut.

## Conséquences

Positif :
- Synchronisation continue : une modification de variable dans le portail CNP est propagée
  dans le cluster sous 5 minutes sans intervention manuelle ni redéploiement explicite.
- Séparation des responsabilités : le backend CNP écrit dans Vault, ESO gère la propagation
  K8s. Le backend ne manipule jamais les `Secret` Kubernetes des apps.
- Cohérent avec le pattern GitOps existant : les `ExternalSecret` sont versionnés dans
  `cnp-gitops` et réconciliés par ArgoCD comme le reste des manifests.
- Applicable aux deux clusters (AKS + k3s) sans adaptation du backend.

Négatif / Dette :
- ESO doit être installé et maintenu sur chaque cluster. Un cluster sans ESO ne peut pas
  recevoir de secrets via ce mécanisme.
- Stakater Reloader est une dépendance supplémentaire dans chaque cluster (légère, ~20 MB).
- Pendant la période transitoire (avant AppRole), le token statique ESO → Vault est un
  secret K8s bootstrappé manuellement : sa rotation n'est pas automatisée.
- Si le chemin Vault n'existe pas encore, l'`ExternalSecret` est en erreur et le pod
  démarre sans les variables attendues. L'`optional: true` atténue l'impact mais ne
  supprime pas le risque si une variable est requise au démarrage.

Neutre :
- Le `refreshInterval: 5m` est un compromis entre fraîcheur et charge sur Vault. Il est
  configurable par app via les values Helm si nécessaire.
- Les `ExternalSecret` générés par le backend sont idempotents : rejouer le provisioning
  GitOps met à jour le manifest sans créer de doublon.
