# Questions fréquentes

## Mon déploiement est bloqué en "Déploiement…" depuis plusieurs minutes.

Vérifiez les logs de votre application. Un pod en `CrashLoopBackOff` indique un crash applicatif. Un pod en `Pending` indique un manque de ressources sur le cluster.

## Comment réduire les coûts quand je n'utilise pas le cluster ?

Utilisez `az aks stop --name cnp-aks-sweden --resource-group cnp-rg` pour arrêter le cluster. Le démarrage prend 3–5 minutes avec `az aks start`.

## Puis-je déployer sur plusieurs clusters en même temps ?

Le multi-cluster est prévu pour la Phase 2. En Phase 1, chaque application est associée à un seul cluster cible.

## Comment ajouter des variables d'environnement secrètes ?

Les secrets sont gérés via Kubernetes Secrets. Depuis la page de votre application, Configuration > Variables d'environnement, les valeurs sont chiffrées au repos.

## Mon image Docker ne se build pas dans la CI GitLab.

Vérifiez que votre `Dockerfile` est à la racine du repo et que le runner GitLab a accès au registry `registry.gitlab.com`.
