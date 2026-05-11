# ADR-0005 : Délimitation des responsabilités entre CI et GitOps

## Statut

- Statut : Accepté
- Date : 2026-05-11

## Contexte

La plateforme CNP orchestre le cycle de vie complet des applications scaffoldées : 
build, test, déploiement, et promotion entre environnements. Deux outils interviennent dans ce cycle :

GitLab CI : pipeline déclenché par les événements Git (push, tag)
ArgoCD : opérateur GitOps tournant dans AKS, qui réconcilie l'état du cluster avec un repo Git de configuration

Sans frontière explicite entre ces deux outils, plusieurs problèmes émergent : duplication de logique de déploiement, 
conflits entre ce que la CI pousse et ce qu'ArgoCD réconcilie, et difficulté à auditer qui a déclenché quel déploiement.
Cet ADR définit la frontière de responsabilité entre CI et GitOps, et documente les trois modes de déploiement exposés aux utilisateurs de la plateforme.

## Décision

La CI est productrice. GitOps est réconciliateur.
La CI ne déploie jamais directement dans Kubernetes en phase 2. Elle produit un artefact (image Docker) et met à jour l'état désiré dans Git. ArgoCD détecte ce changement et applique.
CI (GitLab)                         GitOps (ArgoCD)
-----------                         ---------------
code source                         repo GitOps (état désiré)
    -> lint + tests                     -> surveille en permanence
    -> build image Docker               -> détecte divergence
    -> scan vulnérabilités (Trivy)      -> kubectl apply
    -> push image registry              -> réconcilie le cluster
    -> mise à jour repo GitOps

Responsabilités explicites
ResponsabilitéCI (GitLab CI)GitOps (ArgoCD)Lint / tests unitairesouinonBuild image DockerouinonScan de vulnérabilitésouinonPush registryouinonMise à jour tag image dans repo GitOpsoui (selon mode)nonApply manifests Kubernetesnon (phase 2)ouiRollbacknonoui (revert Git)Détection de driftnonouiSource de vérité infrastructurenonoui (Git)

Structure des repos
Deux repos distincts par application scaffoldée :
Repo applicatif (cnp-platform/mon-service) :
Dockerfile
src/
chart/                    # chart Helm (ADR-0005)
.gitlab-ci.yml            # pipeline CI
Repo GitOps CNP (cnp-platform/cnp-gitops) :
apps/
  mon-service/
    values-dev.yaml       # image.tag mis à jour par la CI
    values-prod.yaml      # mis à jour selon le mode de déploiement
ArgoCD surveille cnp-gitops et déploie chaque app dans son namespace Kubernetes dédié.


## Conséquences

- Le repo cnp-gitops est créé dans le namespace GitLab CNP avant la mise en place d'ArgoCD. Sa structure de répertoires est normalisée : apps/{app-name}/values-{env}.yaml.
- ArgoCD est déployé sur AKS via son chart Helm officiel. Sa configuration (liste des apps à surveiller) est elle-même versionnée dans cnp-gitops (pattern App of Apps).
- Le script update-gitops.sh est maintenu dans un repo partagé CNP et versionné indépendamment des apps scaffoldées.
- Le mode de déploiement est modifiable à tout moment via le portail ou la CLI sans modifier le pipeline CI (le pipeline interroge l'API à chaque exécution).