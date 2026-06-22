# Déployer sur AKS

CNP orchestre le déploiement de vos applications sur Azure Kubernetes Service via GitLab CI et ArgoCD. Le déploiement est déclenché automatiquement à chaque push sur `main` (ou `release-dev-*` pour l'environnement dev).

```bash
# Pusher sur main déclenche la CI, qui build l'image
# et met à jour les manifestes ArgoCD automatiquement
git push origin main
```

> **Info :** Le cluster AKS est en autoscale 2–4 nodes. Utilisez `az aks stop` pour réduire les coûts hors usage.
