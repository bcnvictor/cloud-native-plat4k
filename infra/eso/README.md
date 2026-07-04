# External Secrets Operator + Stakater Reloader (4K-105)

Runbook d'installation d'[External Secrets Operator](https://external-secrets.io) (ESO)
et de [Stakater Reloader](https://github.com/stakater/Reloader) sur les deux clusters CNP
(`cnp-aks` et `cnp-k3s`), prérequis infra de la gestion des variables d'environnement
applicatives ([ADR-0024](../../docs/adr/0024-external-secrets-operator.md),
[ADR-0025](../../docs/adr/0025-env-vars-applicatives.md)).

ESO synchronise en continu `secret/apps/{group}/{app}/{env}` (Vault) vers un `Secret`
Kubernetes natif par app. Stakater Reloader redémarre le `Deployment` concerné quand ce
`Secret` change. Le backend CNP n'écrit jamais directement dans un `Secret` K8s d'app.

Comme pour Tailscale (`infra/aks/tailscale/`) et ArgoCD sur k3s (`infra/oracle/k3s/README.md`),
l'installation est faite à la main via `helm`/`kubectl` — pas de `helm_release` Terraform,
car les CRDs `ClusterSecretStore`/`ExternalSecret` doivent exister avant que les manifests
qui en dépendent puissent être appliqués.

**Statut : déployé et validé en live sur AKS et cnp-k3s (2026-07-04)** — voir « État actuel »
en bas de page.

## Écart avec l'énoncé du ticket

Le critère d'acceptation du smoke test mentionne `secret/cnp/platform`, mais les notes du
même ticket imposent que le token ESO soit restreint à `secret/apps/*` uniquement (pas
d'accès à `secret/cnp/platform` ni `secret/clusters/*`, réservés à la policy `cnp-backend`
du backend). Les deux ne peuvent pas être vrais en même temps : ce runbook applique la
policy restreinte (cohérente avec ADR-0024 §2 et le principe de moindre privilège) et fait
le smoke test sur un chemin de test dédié `secret/apps/_smoke-test/eso` à la place. À
signaler dans le ticket Linear si ça mérite une correction de l'énoncé.

## Dépendance croisée non couverte par 4K-104/105/106/107

Stakater Reloader ne redémarre un `Deployment` que si son template porte l'annotation
`reloader.stakater.com/auto: "true"` (ou une annotation `secret.reloader.stakater.com/reload`
ciblée) — il n'y a pas de mode « reload tout, sans annotation » dans le chart OSS. Le
template Helm applicatif scaffoldé par CNP (repo GitLab `GITLAB_TEMPLATES_NAMESPACE/*`,
hors de ce dépôt) doit donc déclarer cette annotation sur son `Deployment` pour que le
rolling restart décrit en ADR-0024 §3 se produise réellement. Aucun des 4 tickets ne couvre
explicitement cette modification de template — à clarifier avec Victor avant de considérer
4K-104 comme totalement terminé.

## Accès réseau pod → cnp-control (découvert en live, pas dans l'ADR d'origine)

ADR-0024 suppose que les pods du cluster peuvent joindre `cnp-control:8200` "via Tailscale",
par analogie avec le sens `cnp-control → cluster` déjà en place pour ArgoCD/Prometheus/Loki
(ADR-0019). **Ce n'est pas symétrique.** Dans la topologie ADR-0019, seul un pod dédié
(`subnet-router`, sur AKS) est membre du tailnet — il fait du routage IP dans le sens
tailnet → cluster (routes qu'il annonce), pas l'inverse. Un pod applicatif quelconque (ESO
compris) n'a par défaut aucune route vers le tailnet (`100.64.0.0/10`) : ni le hostname
MagicDNS `cnp-control` (le CoreDNS du cluster ne le connaît pas), ni son IP tailnet directe
(`100.85.20.62`, timeout confirmé en test réel sur les deux clusters) ne sont joignables.

**Solution retenue : le mécanisme d'egress de l'opérateur Tailscale Kubernetes.** Un `Service`
Kubernetes annoté `tailscale.com/tailnet-ip: "100.85.20.62"` (voir
`vault-egress-service.yaml`) fait provisionner par l'opérateur un pod-proxy (`ts-vault-cnp-control-*`,
namespace `tailscale`) que n'importe quel pod du cluster peut joindre via ce `Service` normal
(`vault-cnp-control.external-secrets.svc.cluster.local:8200`), qui relaie ensuite vers
`cnp-control` sur le tailnet. C'est le mécanisme officiel prévu par Tailscale pour "pod de
cluster → device sur le tailnet" — pas de bricolage de routes IP.

Deux clusters, deux situations de départ différentes :
- **AKS** avait déjà l'opérateur Tailscale (installé pour 4K-45/Tailscale, `infra/aks/tailscale/`) : on a juste ajouté le `Service` egress.
- **cnp-k3s** n'avait aucun opérateur Tailscale : on en a installé un nouveau dédié
  (`infra/oracle/k3s/tailscale/operator-values.yaml`), avec le même client OAuth que sur AKS
  (mêmes credentials, deux devices tailnet distincts).

### Deux blocages ACL Tailscale rencontrés (comptes larges, hors de ce repo)

La policy ACL Tailscale (console, ou API `GET/POST /api/v2/tailnet/-/acl`) a dû être corrigée
deux fois avant que l'egress fonctionne :

1. **`tagOwners`** : `tag:k8s` n'était attribuable que par `autogroup:admin` (un humain
   connecté). Un OAuth client (comme celui de l'opérateur) n'appartient jamais à
   `autogroup:admin`, donc l'opérateur ne pouvait pas déléguer `tag:k8s` aux pods-proxy qu'il
   crée — même si le client OAuth lui-même avait `tag:k8s` coché dans ses propres scopes
   (ce sont deux vérifications distinctes). Fix : ajouter `"tag:k8s"` comme propriétaire de
   lui-même dans `tagOwners`.
2. **`acls`** : la règle réseau `tag:k8s → tag:cnp-control` n'autorisait que les ports `443`
   et `8000` (ArgoCD/backend CNP existants), pas `8200` (Vault). Fix : ajouter `8200` à cette
   règle.

Policy ACL finale (pour référence, gérée dans la console Tailscale — **pas dans ce repo**) :

```json
{
  "acls": [
    {"action":"accept","src":["tag:cnp-control"],"dst":["10.0.0.0/16:9090","10.0.0.0/16:3100","10.0.0.0/16:443","10.0.0.0/16:6443"]},
    {"action":"accept","src":["tag:cnp-control"],"dst":["tag:k8s:9090","tag:k8s:3100","tag:k8s:443","tag:k8s:6443"]},
    {"action":"accept","src":["tag:k8s"],"dst":["tag:cnp-control:443","tag:cnp-control:8000","tag:cnp-control:8200"]}
  ],
  "autoApprovers": {"routes": {"10.0.0.0/16": ["tag:k8s"]}},
  "tagOwners": {
    "tag:cnp-control": ["autogroup:admin"],
    "tag:k8s": ["autogroup:admin", "tag:k8s"],
    "tag:k8s-operator": ["autogroup:admin"]
  }
}
```

> Si l'IP tailnet de `cnp-control` (`100.85.20.62`) change un jour (ré-enrôlement, VM
> recréée), il faut mettre à jour `tailscale.com/tailnet-ip` dans `vault-egress-service.yaml`
> sur les deux clusters.

## Composants installés

| Namespace           | Cluster(s)      | Contenu                                                          |
|---------------------|-----------------|-------------------------------------------------------------------|
| `external-secrets`  | AKS + cnp-k3s   | ESO + `ClusterSecretStore vault-backend` + `Service` egress `vault-cnp-control` |
| `tailscale`         | AKS + cnp-k3s   | Opérateur Tailscale K8s + pod-proxy egress `ts-vault-cnp-control-*` |
| `reloader`          | AKS + cnp-k3s   | Stakater Reloader                                                  |

---

## 1. Créer la policy Vault `eso-reader` + le token statique

Une seule fois, sur `cnp-control` (voir conventions dans
[`docs/guides/vault-runbook.md`](../../docs/guides/vault-runbook.md)). `docker compose exec`
alloue un TTY par défaut, ce qui casse le heredoc — passer `-T` :

```bash
cd ~/cloud-native-plat4k

docker compose exec -T -e VAULT_ADDR=http://127.0.0.1:8200 -e VAULT_TOKEN=<root_token> vault \
  vault policy write eso-reader - << 'EOF'
path "secret/data/apps/*" {
  capabilities = ["read"]
}
path "secret/metadata/apps/*" {
  capabilities = ["read", "list"]
}
EOF
```

Générer le token statique (transitoire, avant migration AppRole — voir ADR-0024 §2) :

```bash
docker compose exec -T -e VAULT_ADDR=http://127.0.0.1:8200 -e VAULT_TOKEN=<root_token> vault \
  vault token create -policy=eso-reader -period=720h -format=json
```

> Le `period` demandé peut être plafonné par le `max_ttl` effectif de Vault (constaté : 768h
> max, même en demandant plus) — pas bloquant, juste à surveiller pour le renouvellement.

Copier le `client_token` (`hvs.xxx...`) — un seul suffit, réutilisé sur les deux clusters.

## 2. Installer ESO

Sur AKS :

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm repo update

helm install external-secrets external-secrets/external-secrets \
  --namespace external-secrets --create-namespace \
  --kube-context cnp-aks
```

Sur `cnp-k3s` :

```bash
helm install external-secrets external-secrets/external-secrets \
  --namespace external-secrets --create-namespace \
  --kubeconfig infra/oracle/k3s/cnp-k3s.yaml
```

Vérifier que les pods sont `Running` **et `1/1`** sur chaque cluster avant de continuer
(le cert-controller et le webhook mettent ~30-50s à devenir `Ready`) :

```bash
kubectl -n external-secrets get pods --context cnp-aks
kubectl -n external-secrets get pods --kubeconfig infra/oracle/k3s/cnp-k3s.yaml
```

> Le chart ESO récent sert les CRDs en `external-secrets.io/v1` — `v1beta1` est **déprécié et
> non servi**. Tous les manifests de ce dossier utilisent `v1`. Si `kubectl apply` répond
> `no matches for kind ... ensure CRDs are installed first` alors que le CRD existe bien
> (`kubectl get crd | grep external-secrets`), c'est probablement le cache de découverte de
> `kubectl` qui est périmé — un simple retry suffit généralement.

## 3. Stocker le token Vault comme `Secret` K8s (par cluster)

Pas de fichier avec le vrai token sur disque — commande impérative directement
(voir `vault-eso-token-secret.example.yaml` pour la forme attendue) :

```bash
kubectl create secret generic vault-eso-token \
  --namespace external-secrets \
  --from-literal=token=<eso_token> \
  --context cnp-aks

kubectl create secret generic vault-eso-token \
  --namespace external-secrets \
  --from-literal=token=<eso_token> \
  --kubeconfig infra/oracle/k3s/cnp-k3s.yaml
```

## 4. Installer l'opérateur Tailscale K8s (si absent) + le `Service` egress

**Sur AKS**, l'opérateur est déjà installé (`infra/aks/tailscale/`) — passer directement à
l'application du `Service` egress.

**Sur `cnp-k3s`**, il faut d'abord l'installer (mêmes credentials OAuth que sur AKS — même
`client_id`, `tag:k8s` déjà autorisé dans ses scopes) :

```bash
helm repo add tailscale https://pkgs.tailscale.com/helmcharts
helm repo update

helm install tailscale-operator tailscale/tailscale-operator \
  --namespace tailscale --create-namespace \
  --values infra/oracle/k3s/tailscale/operator-values.yaml \
  --set oauth.clientId=<TS_OAUTH_CLIENT_ID> \
  --set oauth.clientSecret=<TS_OAUTH_CLIENT_SECRET> \
  --kubeconfig infra/oracle/k3s/cnp-k3s.yaml
```

Puis, sur les deux clusters, le `Service` egress vers Vault (voir « Accès réseau pod →
cnp-control » ci-dessus pour le pourquoi, et vérifier au préalable que la policy ACL
Tailscale autorise bien `tag:k8s → tag:cnp-control:8200`) :

```bash
kubectl apply -f infra/eso/vault-egress-service.yaml --context cnp-aks
kubectl apply -f infra/eso/vault-egress-service.yaml --kubeconfig infra/oracle/k3s/cnp-k3s.yaml
```

Vérifier qu'un pod-proxy `ts-vault-cnp-control-*` apparaît `1/1 Running` dans le namespace
`tailscale` sur chaque cluster :

```bash
kubectl get pods -n tailscale --context cnp-aks
kubectl get pods -n tailscale --kubeconfig infra/oracle/k3s/cnp-k3s.yaml
```

## 5. Appliquer le `ClusterSecretStore`

```bash
kubectl apply -f infra/eso/cluster-secret-store.yaml --context cnp-aks
kubectl apply -f infra/eso/cluster-secret-store.yaml --kubeconfig infra/oracle/k3s/cnp-k3s.yaml
```

Vérifier `status.conditions[].reason == Valid` sur chaque cluster :

```bash
kubectl get clustersecretstore vault-backend --context cnp-aks -o jsonpath='{.status.conditions[0].reason}{" "}{.status.conditions[0].message}{"\n"}'
kubectl get clustersecretstore vault-backend --kubeconfig infra/oracle/k3s/cnp-k3s.yaml -o jsonpath='{.status.conditions[0].reason}{" "}{.status.conditions[0].message}{"\n"}'
```

Si l'erreur est `dial tcp: lookup ... no such host` ou `context deadline exceeded`, voir la
section « Accès réseau pod → cnp-control » — le `Service` egress (étape 4) n'est probablement
pas encore en place ou pas encore `Ready`.

## 6. Installer Stakater Reloader

```bash
helm repo add stakater https://stakater.github.io/stakater-charts
helm repo update

helm install reloader stakater/reloader \
  --namespace reloader --create-namespace \
  --kube-context cnp-aks

helm install reloader stakater/reloader \
  --namespace reloader --create-namespace \
  --kubeconfig infra/oracle/k3s/cnp-k3s.yaml
```

## 7. Smoke test

Seeder une valeur de test dans Vault (chemin dédié, voir « Écart avec l'énoncé du ticket ») :

```bash
docker compose exec -T -e VAULT_ADDR=http://127.0.0.1:8200 -e VAULT_TOKEN=<root_token> vault \
  vault kv put secret/apps/_smoke-test/eso FOO=bar
```

Appliquer l'`ExternalSecret` de test sur les deux clusters :

```bash
kubectl apply -f infra/eso/test-external-secret.yaml --context cnp-aks
kubectl apply -f infra/eso/test-external-secret.yaml --kubeconfig infra/oracle/k3s/cnp-k3s.yaml
```

Vérifier la synchronisation (`SecretSynced` et présence du `Secret` K8s) :

```bash
kubectl get externalsecret eso-smoke-test -n external-secrets --context cnp-aks -o jsonpath='{.status.conditions[0].reason}{"\n"}'
kubectl get secret eso-smoke-test -n external-secrets --context cnp-aks -o jsonpath='{.data.FOO}' | base64 -d; echo
```

Nettoyage post-test :

```bash
kubectl delete -f infra/eso/test-external-secret.yaml --context cnp-aks
kubectl delete -f infra/eso/test-external-secret.yaml --kubeconfig infra/oracle/k3s/cnp-k3s.yaml

docker compose exec -T -e VAULT_ADDR=http://127.0.0.1:8200 -e VAULT_TOKEN=<root_token> vault \
  vault kv metadata delete secret/apps/_smoke-test/eso
```

---

## État actuel (référence)

> Mis à jour le 2026-07-04, après exécution live complète.

| Étape                                                    | AKS | cnp-k3s |
|-----------------------------------------------------------|-----|---------|
| Policy Vault `eso-reader` créée                            | OK  | (partagée, une seule instance Vault) |
| Token ESO généré                                           | OK  | (même token réutilisé) |
| ESO installé (namespace `external-secrets`)                | OK  | OK      |
| `Secret vault-eso-token` créé                              | OK  | OK      |
| Opérateur Tailscale K8s présent                            | OK (préexistant, 4K-45) | OK (installé pour 4K-105) |
| `Service` egress `vault-cnp-control` + pod-proxy `Running`  | OK  | OK      |
| Policy ACL Tailscale corrigée (`tagOwners` + port 8200)     | OK (compte partagé, s'applique aux deux) | OK |
| `ClusterSecretStore vault-backend` `Valid`                 | OK  | OK      |
| Stakater Reloader installé (namespace `reloader`)          | OK  | OK      |
| Smoke test `eso-smoke-test` synchronisé (`SecretSynced`)   | OK  | OK      |

## Cleanup complet (désinstallation)

```bash
helm uninstall external-secrets -n external-secrets --kube-context cnp-aks
helm uninstall reloader -n reloader --kube-context cnp-aks
kubectl delete svc vault-cnp-control -n external-secrets --context cnp-aks
kubectl delete ns external-secrets reloader --context cnp-aks
# Ne PAS supprimer le namespace tailscale sur AKS : l'opérateur y était déjà avant 4K-105 (4K-45)

helm uninstall external-secrets -n external-secrets --kubeconfig infra/oracle/k3s/cnp-k3s.yaml
helm uninstall reloader -n reloader --kubeconfig infra/oracle/k3s/cnp-k3s.yaml
helm uninstall tailscale-operator -n tailscale --kubeconfig infra/oracle/k3s/cnp-k3s.yaml
kubectl delete ns external-secrets reloader tailscale --kubeconfig infra/oracle/k3s/cnp-k3s.yaml
```
