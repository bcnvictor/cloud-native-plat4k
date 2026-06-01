# ADR-0011 : Modèle GitOps avec ArgoCD (App of Apps & Multiple Sources)

## Statut

- Statut : Accepté
- Date : 2026-06-01

## Contexte

Conformément à l'ADR-0005, la Phase 2 de la Cloud Native Platform (CNP) acte l'utilisation d'ArgoCD comme moteur de réconciliation GitOps sur notre cluster AKS. La CI est responsable de la production des images Docker, et ArgoCD est responsable de leur déploiement.

Avant d'intégrer pleinement ce modèle dans notre backend (scaffolding et import d'apps), nous devions valider via le Spike GitOps (4K-35) que l'architecture répondait à nos contraintes opérationnelles, notamment :
- L'automatisation du déploiement sans intervention manuelle.
- La séparation nette entre le code de l'application (et son chart Helm générique) et les valeurs de configuration spécifiques aux environnements.
- La résilience de l'état (survie aux arrêts/relances du cluster pour raisons de coûts).
- La capacité à gérer tous les environnements avec un seul dépôt GitOps sans utiliser le branching par environnement.

## Décision

Nous avons décidé d'implémenter l'architecture GitOps suivante autour d'ArgoCD :

1. **Dépôt central unique (`cnp-gitops`)** : Nous utilisons un seul dépôt pour centraliser l'état désiré de l'ensemble de l'infrastructure et des applications. Les environnements (dev, prod) sont séparés par des dossiers de configuration (ex: `apps/mon-app/values-dev.yaml`) et non par des branches Git.
2. **Pattern *App of Apps*** : ArgoCD est configuré au démarrage (bootstrap) via une unique "Application racine" (`root-app.yaml`). Cette application observe le dossier `argocd/` du dépôt `cnp-gitops`. Dès qu'un nouveau fichier YAML est ajouté dans ce dossier (déclarant une nouvelle application), ArgoCD le découvre et déploie l'application automatiquement.
3. **Fonctionnalité *Multiple Sources*** : Les manifestes ArgoCD utilisent la fonctionnalité multi-sources (introduite dans ArgoCD v2.6+). ArgoCD assemble dynamiquement deux sources lors du déploiement :
   - La source 1 : Le Chart Helm générique, tiré directement du dépôt GitLab de l'application (ex: `cnp-demo-app`).
   - La source 2 : Le fichier de surcharges de valeurs (`values-{env}.yaml`), tiré du dépôt central `cnp-gitops`.

## Conséquences

**Positif :**
- L'infrastructure as Code (IaC) est centralisée, offrant une auditabilité et une traçabilité totales.
- Le pattern *App of Apps* permet à la plateforme CNP de déployer de nouvelles applications en générant simplement un fichier YAML dans le dossier `argocd/` sans interagir avec l'API Kubernetes ni reconfigurer ArgoCD.
- L'utilisation des *Multiple Sources* nous évite de dupliquer les charts Helm. Le développeur garde la main sur la structure de son chart dans son dépôt applicatif, tandis que la plateforme garde le contrôle sur la configuration des environnements (répliques, limites CPU/RAM).
- La dérive d'infrastructure (*Drift*) et l'auto-healing sont gérés nativement et ont été validés avec succès sur AKS. L'état survit aux arrêts/relances du cluster.

**Négatif / Dette :**
- Une complexité supplémentaire dans la chaîne de déploiement (nouveau composant critique dans le cluster).
- Le backend CNP (API) devra être mis à jour pour interagir avec le dépôt Git (via l'API GitLab) afin de créer/modifier les manifestes ArgoCD au lieu d'appeler directement le client Kubernetes Python (`k8s/client.py`), constituant un chantier majeur pour la suite de la Phase 2.

**Neutre :**
- La gestion des secrets (identifiants bases de données, tokens externes) n'est pas couverte par ce modèle et nécessitera l'utilisation d'une solution annexe (ex: External Secrets Operator ou Azure Key Vault) faisant l'objet d'un autre ADR.
