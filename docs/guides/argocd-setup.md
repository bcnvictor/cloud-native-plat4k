# Guide Opérationnel : Setup ArgoCD et Scénarios GitOps

Ce guide documente l'installation d'ArgoCD sur le cluster AKS et les scénarios de validation de bout en bout exécutés dans le cadre du Spike GitOps v1 (4K-37). Il permet de vérifier que le comportement attendu d'ArgoCD (App of Apps, Sync, Auto-Heal) fonctionne correctement sur la Cloud Native Platform (CNP).

## 1. Installation Initiale d'ArgoCD

Prérequis : Vous devez être connecté au cluster AKS (via `az aks get-credentials`). ArgoCD **v2.6 minimum** est requis — la feature `sources[]` avec `ref:` (utilisée dans tous nos manifestes d'application) n'existe pas avant cette version.

```bash
# 1. Création du namespace dédié
kubectl create namespace argocd

# 2. Déploiement d'ArgoCD via son manifest officiel
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# 3. Récupération du mot de passe initial de l'interface web (l'utilisateur est 'admin')
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d; echo

# 4. Accès à l'UI (Port-forward)
kubectl port-forward svc/argocd-server -n argocd 8080:443
# Naviguer sur https://localhost:8080
```

## 2. Bootstrapping avec le dépôt `cnp-gitops`

L'initialisation de notre modèle *App of Apps* se fait en appliquant un seul fichier racine (créé dans le ticket 4K-36).

```bash
# Appliquer l'application racine
kubectl apply -f cnp-gitops/bootstrap/root-app.yaml
```
Dès son application, ArgoCD va automatiquement scanner le dossier `argocd/` du dépôt `cnp-gitops` et déployer les sous-applications (comme `cnp-demo-app-dev` et `cnp-demo-app-prod`).

---

## 3. Scénarios de Validation (Critères d'Acceptation 4K-37)

Ces scénarios ont été conçus pour prouver la résilience de notre architecture GitOps sur AKS.

### Scénario 1 : Sync Auto (Commit Values → Re-déploiement < 3 min)
**Objectif :** Vérifier que la modification d'une surcharge d'environnement est appliquée.
1. Dans le dépôt `cnp-gitops`, modifier `apps/cnp-demo-app/values-dev.yaml`.
2. Changer `replicas: 1` à `replicas: 2`.
3. Commiter et pousser la modification.
4. **Validation :** Dans les 3 minutes (délai de poll par défaut d'ArgoCD), l'interface d'ArgoCD doit afficher la synchronisation, et la commande `kubectl get pods -n dev` doit afficher 2 pods.

### Scénario 2 : Détection de Drift (SelfHeal)
**Objectif :** Vérifier que toute modification manuelle sur le cluster est écrasée.
1. Simuler une erreur humaine sur le cluster en supprimant un service ou en modifiant un déploiement manuellement :
   ```bash
   kubectl scale deployment cnp-demo-app -n dev --replicas=0
   ```
2. **Validation :** Immédiatement, ArgoCD détecte l'état *Out of Sync*. Puisque l'option `selfHeal: true` est configurée dans nos manifestes, ArgoCD annule automatiquement la modification et recrée les répliques pour correspondre à Git.

### Scénario 3 : Rollback via Git
**Objectif :** Vérifier que la procédure de retour arrière est gérée par Git.
1. Exécuter un `git revert` sur le commit précédent (celui qui a passé les répliques à 2).
2. Pousser vers la branche `main` du dépôt `cnp-gitops`.
3. **Validation :** ArgoCD resynchronise et ramène le nombre de pods à 1, démontrant que l'historique Git est la seule source de vérité.

### Scénario 4 : Prune (Suppression de ressource)
**Objectif :** Vérifier que la suppression d'un fichier YAML dans Git nettoie le cluster.
1. Supprimer le fichier `argocd/cnp-demo-app/dev.yaml` du dépôt Git et pousser.
2. **Validation :** ArgoCD supprime la sous-application de son interface et déclenche la suppression de toutes les ressources du namespace `dev` grâce au finalizer `resources-finalizer.argocd.argoproj.io`.

### Scénario 5 : Résilience Stop/Start AKS
**Objectif :** Vérifier que l'extinction du cluster (pour économies) ne casse pas l'état GitOps.
1. Stopper les nœuds AKS via le script de la plateforme : `./scripts/aks-stop.sh`.
2. Démarrer le cluster le lendemain : `./scripts/aks-start.sh`.
3. **Validation :** Une fois les pods système remontés, le contrôleur ArgoCD redémarre. Il revérifie l'état du cluster par rapport à Git et relance les déploiements de `cnp-demo-app` automatiquement, sans intervention humaine.

---

## Apprentissages et Notes
- **Pas de branche par environnement** : Le modèle *Multiple Sources* avec un dossier par application (`apps/`) s'est révélé beaucoup plus stable et facile à tracer que le branching par environnement.
- **Mécanisme `$ref` dans Multiple Sources** : Quand une source porte `ref: <nom>`, elle devient une source de référence (pas de déploiement direct) et expose son contenu sous la variable `$<nom>`. Les autres sources peuvent alors l'utiliser dans leurs `valueFiles` (ex: `$gitops/apps/my-app/values-dev.yaml`). `$<nom>` pointe toujours sur la **racine** du repo référencé, indépendamment de tout champ `path`. Cette feature requiert ArgoCD v2.6+.
- L'utilisation des finalizers est vitale pour éviter de laisser des ressources orphelines, surtout sur un cluster AKS aux ressources limitées.
- **Sécurité** : Aucune clé Kubernetes n'a eu besoin d'être exportée vers GitLab pour le déploiement. L'AKS vient tirer l'état lui-même.
