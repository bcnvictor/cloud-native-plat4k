# Guide opérationnel : Cluster AKS v1

## Prérequis

- [Azure CLI](https://docs.microsoft.com/cli/azure/install-azure-cli) installé
- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.6 installé
- [kubectl](https://kubernetes.io/docs/tasks/tools/) installé
- Abonnement Azure actif (Azure Student)

## 1. Connexion Azure

```bash
az login
az account show
```

Si plusieurs abonnements :
```bash
az account list
az account set --subscription "<le bon abonnement>"
```

## 2. Provisioning du cluster 
(C que la première fois et si pb. Ce cluster est déja up)

```bash
cd infra/aks/

terraform init
terraform plan
terraform apply
```

## 3. Récupération du kubeconfig

```bash
az aks get-credentials \
  --resource-group cnp-rg \
  --name cnp-aks \
  --overwrite-existing

kubectl get nodes   # doit afficher 2 nodes en état Ready
```

Le kubeconfig est écrit dans `~/.kube/config`. kubectl l'utilise automatiquement.

## 4. Exporter le kubeconfig pour le backend FastAPI

Le backend a besoin du kubeconfig via une variable d'environnement :

```bash
# Exporter le kubeconfig en base64 pour l'injecter comme secret Kubernetes
terraform output -raw kubeconfig > kubeconfig.yaml

# Ne pas commiter ce fichier (il est dans .gitignore)
```

En local, ajouter dans le `.env` du backend :
```
KUBECONFIG_PATH=/chemin/absolu/vers/kubeconfig.yaml
```

En production (dans AKS), injecter via un Kubernetes Secret (voir ADR-0002).

## 5. Start / Stop du cluster (économie de credits)

```bash
# Arrêter les nodes (stoppe la facturation VMs, ~0.08 USD/h économisés)
./scripts/aks-stop.sh

# Redémarrer les nodes
./scripts/aks-start.sh
```

Note : le control plane AKS reste actif même a 0 nodes (~0.10 USD/h fixe sur abonnement Student - souvent gratuit).

## 6. Destruction complète

Pour tout supprimer proprement et libérer les ressources Azure :

```bash
cd infra/aks/
terraform destroy   # taper 'yes' pour confirmer
```

Cela supprime le resource group et tout ce qu'il contient (cluster, IPs, disques).

## 7. Vérification post-provisioning

```bash
kubectl get nodes                          # 2 nodes Ready
kubectl get namespaces                     # default, kube-system, kube-public
kubectl top nodes                          # métriques CPU/RAM (après déploiement metrics-server)
```

## 8. Prochaines étapes après provisioning

1. Déployer nginx-ingress-controller (une IP publique pour toutes les apps)
2. Déployer kube-prometheus-stack (monitoring)
3. Déployer la CNP elle-même (backend + frontend) dans le namespace `cnp`
4. Créer les namespaces `dev` et `prod` pour les apps utilisateurs
