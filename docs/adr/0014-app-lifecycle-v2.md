# ADR-0014 : Provisioning GitOps CI-driven et cycle de vie complet des apps

## Statut

Accepted
- Date : 2026-06-09
- Ticket : 4K-59

## Contexte

Avant ce changement, le provisioning ArgoCD (création des manifestes `argocd/<app>/` et des values `apps/<app>/` dans `cnp-gitops`) était effectué par le backend Python au moment du scaffold, via `backend/gitops/provisioner.py` appelé dans `app_service.py`.

Cela créait une **race condition systématique** : ArgoCD découvrait l'application immédiatement après le commit d'injection CI, avec `image.tag: none`, avant que la première image Docker soit buildée. Résultat : `ImagePullBackoff` immédiat, nécessitant une intervention manuelle (resync ArgoCD après le premier build).

Par ailleurs, la suppression d'une app ne nettoyait que la base de données — les manifestes ArgoCD et le projet GitLab scaffoldé restaient orphelins.

## Décision

### 1. Provisioning déplacé dans la CI (`update-gitops` idempotent)

Le job `update-gitops` de `cnp-ci-modules` est rendu **idempotent** : à chaque exécution, il crée les fichiers `argocd/<app>/<env>.yaml` et `apps/<app>/values-<env>.yaml` dans `cnp-gitops` s'ils n'existent pas encore, puis met à jour le tag image.

ArgoCD ne découvre donc l'application qu'après le premier run de `update-gitops`, qui ne s'exécute lui-même qu'après le push Docker. La race condition est structurellement impossible.

Ce mécanisme remplace `provisioner.py`, qui est supprimé.

### 2. Scoping du tag par branche

Le job `update-gitops` provisionne toujours les deux environnements (`dev` et `prod`) pour garantir que les manifestes ArgoCD existent dès le premier CI, mais **n'écrit le tag image que dans l'environnement correspondant à la branche** :

- `main` / `master` → mise à jour de `values-prod.yaml`
- `release-dev-*` → mise à jour de `values-dev.yaml`

### 3. `skip_first_deploy` inchangé dans son effet

L'option `skip_first_deploy` au scaffold contrôle toujours le message du commit d'injection :

- `false` (défaut) → `"ci: inject CNP pipeline"` → CI s'exécute → `update-gitops` provisionne + déploie
- `true` → `"ci: inject CNP pipeline [skip ci]"` → CI skippée → ArgoCD ne découvre pas l'app jusqu'au prochain push manuel

### 4. Suppression enrichie

L'endpoint `DELETE /api/v1/apps/{id}` effectue désormais trois opérations en séquence :

1. **Cleanup GitOps** : supprime `argocd/<app>/` et `apps/<app>/` dans `cnp-gitops` via l'API Commits GitLab (atomic)
2. **Suppression du projet GitLab** : uniquement si `origin = scaffolded` (les repos importés ne sont pas supprimés)
3. **Suppression en base**

Les échecs des étapes 1 et 2 sont loggués mais n'empêchent pas la suppression en base — l'app disparaît du portail même en cas d'artefact GitLab orphelin.

## Conséquences

Positif :
- Race condition `ImagePullBackoff` éliminée structurellement — ArgoCD ne voit l'app que quand une image valide existe
- Suppression propre : pas de manifestes ni de repos orphelins après delete
- `provisioner.py` supprimé — moins de surface de code, responsabilité CI/backend mieux délimitée
- Le provisioning est rejoué automatiquement si `cnp-gitops` est en retard ou corrompu (idempotent)

Négatif / Dette :
- `apk add yq` installé à l'exécution dans `update-gitops` (réseau APK requis) — à bake dans une image `cnp-ci-tools` dédiée (prévu)
- Les échecs de cleanup GitLab/GitOps sont silencieux côté utilisateur — amélioration UX prévue (retour d'état dans la réponse DELETE)
- Le provisioning ne se déclenche que sur `main` et `release-dev-*` (règles du job `update-gitops`) — un scaffold suivi d'un push sur une autre branche ne provisionne pas ArgoCD

## Références

- ADR-0005 : délimitation CI / GitOps
- ADR-0011 : injection CI et comportement `skip_first_deploy`
