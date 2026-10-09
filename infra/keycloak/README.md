# Keycloak portable pour CNP

Une instance par cluster, un domaine HTTPS commun, un préfixe stable par instance.
Les profils `public` et `private` sont indépendants du fournisseur. Les cibles
`public-aks.yaml` et `private-k3s.yaml` sont des exemples concrets à adapter.
Le chart installe Keycloak et son stockage PostgreSQL dédié. Il réutilise
Vault, ESO, Tailscale et la passerelle NGINX de la CNP.

## Prérequis

- kubectl avec le contexte explicite de la cible ; Helm **3.17.3**, uv, SSH ;
- cluster déjà enregistré dans CNP sous `cnp_cluster_name` ; backend avec la
  migration du registre d'instances et l'API administrateur ;
- ESO avec les CRD `external-secrets.io/v1` ; opérateur Tailscale dans `tailscale` ;
- egress Vault déjà installé (`infra/eso/README.md`) et connectivité ESO→Vault ;
- ACL Tailscale autorisant la VM CNP vers les proxies `tag:k8s` sur 8080,
  et proxies vers Vault 8200 ; identifiants OAuth de l'opérateur déjà autorisés ;
- StorageClass de la cible disponible ; DNS public auth vers la VM CNP ;
- VM joignable en SSH par `gateway_host`, dépôt à `gateway_repo_path`, montage
  des routes et template auth dans le service existant `nginx-grafana` ;
- certificat auth dans les volumes Certbot existants. Sur la VM, définir
  `AUTH_DOMAIN=auth.cloud-native-plat4k.me`, `CERTBOT_EMAIL`, puis exécuter
  `infra/keycloak/gateway/init-tls.sh`. Le frontend HTTP existant doit servir
  `/.well-known/acme-challenge/` depuis le volume `certbot_webroot`.

L'absence du certificat auth n'empêche pas Grafana de démarrer. La commande de
bootstrap refuse de poursuivre tant que le certificat n'est pas disponible.
Les conteneurs backend et passerelle doivent résoudre MagicDNS et joindre le
tailnet. La passerelle utilise le DNS Tailscale ; vérifier aussi le backend.

## Installation ou relance

Les secrets opérateur viennent de l'environnement ou du gestionnaire de secrets,
sans fichier `.env` supplémentaire. Ne pas les passer sur la ligne de commande.

```bash
export TAILNET_DOMAIN=tail-example.ts.net
# VAULT_ADDR, VAULT_TOKEN : Vault opérateur avec droits bootstrap/policies/token.
# CNP_API_URL, CNP_API_KEY : API CNP de validation, clé d'un administrateur.
# CNP_BACKEND_VAULT_POLICY : optionnel, défaut cnp-backend.
# CNP_HELM : optionnel, chemin du binaire Helm 3.17.3.
./infra/keycloak/deploy.sh --config infra/keycloak/targets/public-aks.yaml --check
./infra/keycloak/deploy.sh --config infra/keycloak/targets/public-aks.yaml
```

Le contrôle `--check` ne modifie ni Vault, ni Kubernetes, ni NGINX, ni le registre.
Le déploiement crée les secrets avec CAS=0, un token ESO par instance, et étend
uniquement la policy backend nommée en conservant ses règles. Il ne modifie pas
la policy de lecture applicative. Le token ESO ne lit que `database/bootstrap` ;
le provisioner est lu par le backend. Un CronJob quotidien renouvelle le token
périodique sans l'inclure dans ses arguments. Surveiller les Jobs en échec :
une interruption de plus de 30 jours nécessite un remplacement contrôlé du
token ESO, pas des mots de passe DB/bootstrap.

Ordre : prérequis → secrets → nouvelle instance inactive → installation →
client technique → Vault → route NGINX validée → issuer public → activation CNP.
Une instance déjà active reste active pendant la relance. Une erreur est
reprenable : relancer après correction. Les mots de passe et le secret du
client technique sont conservés ; une divergence est refusée.

Les données du PVC survivent à Helm uninstall et au prune ArgoCD. L'installation
sur un cluster neuf avec des secrets cohérents fonctionne, mais elle ne restaure
pas les utilisateurs et sessions d'un ancien PVC. Une reprise avec identités
requiert une sauvegarde/restauration de la base Keycloak, hors de cette procédure.
La commande ne recrée pas automatiquement les realms des applications existantes.

## Cloud privé et nouvelle cible

Depuis la VM ayant le kubeconfig k3s, employer `private-k3s.yaml`. Remplacer le
contexte, le nom CNP, les paramètres SSH/tailnet et StorageClass selon le site.
Pour un nouveau cloud, copier une cible et garder le profil public ou privé.
La clé d'instance reste la même lors d'un changement de cloud : son issuer ne
change pas. Un changement d'association d'une app déjà liée n'est pas implicite.

## ArgoCD

Passer la cible en `mode: argocd` avec `argo_application`. Publier d'abord le
commit plateforme contenant le chart. Générer ensuite l'Application avec son SHA
complet, jamais `HEAD` :

```bash
uv run --no-project --python 3.11 --with-requirements infra/keycloak/requirements.lock \
  python -m infra.keycloak.argocd.render --config infra/keycloak/targets/public-aks.yaml \
  --revision <SHA_COMPLET_PUBLIE> > /tmp/keycloak-public-01.yaml
```

Le générateur vérifie que le commit existe sur GitHub. Fournir `GITHUB_TOKEN`
uniquement si nécessaire à cette lecture. L'accès de lecture ArgoCD au dépôt
utilise un Secret repository existant ; aucun token dans les Applications.
Après vérification de cet accès, intégrer les fichiers générés dans
`cnp-gitops/argocd/cnp-aks/keycloak.yaml` et `cnp-k3s/keycloak.yaml`.
Le déploiement demande alors une sync et observe la disponibilité pendant au
plus 10 minutes. Il refuse un Helm concurrent sur une installation ArgoCD.
Aucune Application n'est publiée avec une révision fictive.

## État de validation

Consulter `docs/guides/keycloak-deployment-validation.md` pour les résultats
réels et les contrôles restant ouverts. Les tests de rendu ne prouvent pas un
login navigateur ni la disponibilité du stockage sur un cluster réel.
