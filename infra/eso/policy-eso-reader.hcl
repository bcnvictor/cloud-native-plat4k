# Policy Vault pour le token statique ESO (4K-105 / ADR-0024).
#
# Un seul token (et donc une seule policy) partagé par tous les clusters
# (cnp-aks, cnp-gke, cnp-k3s) : ClusterSecretStore "vault-backend".
#
# Lecture seule sur secret/apps/* et sur le seul chemin plateforme
# secret/platform/external-dns — jamais sur secret/cnp/platform ni
# secret/clusters/* (réservés à la policy cnp-backend du backend CNP).
# ESO ne doit jamais pouvoir écrire ni supprimer : la seule source d'écriture
# sur secret/apps/* est le backend CNP (ADR-0025), et secret/platform/external-dns
# est écrit à la main par un opérateur (token root).
#
# Appliquer (opérateur, token root, sur cnp-control) : voir infra/eso/README.md
# étape 1. `vault policy write` remplace la policy entière : toujours écrire
# ce fichier complet, jamais un extrait.

path "secret/data/apps/*" {
  capabilities = ["read"]
}

# ESO a besoin de lire les métadonnées (versions) pour détecter les mises à
# jour lors de la réconciliation périodique (refreshInterval).
path "secret/metadata/apps/*" {
  capabilities = ["read", "list"]
}

# Token API Cloudflare d'external-dns (clé cloudflare_api_token), synchronisé sur
# chaque cluster dans le Secret external-dns/cloudflare-api-token par le chart
# infra/external-dns/cloudflare-token. Chemin exact (pas de glob) : ESO ne doit
# rien lire d'autre sous secret/platform/.
path "secret/data/platform/external-dns" {
  capabilities = ["read"]
}

# Métadonnées du même secret uniquement (pas de "list" : aucun parcours de
# secret/platform/).
path "secret/metadata/platform/external-dns" {
  capabilities = ["read"]
}
