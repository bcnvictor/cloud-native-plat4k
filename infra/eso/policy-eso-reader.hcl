# Policy Vault pour le token statique ESO (4K-105 / ADR-0024).
#
# Lecture seule sur secret/apps/* uniquement — jamais sur secret/cnp/platform
# ni secret/clusters/* (réservés à la policy cnp-backend du backend CNP).
# ESO ne doit jamais pouvoir écrire ni supprimer : la seule source d'écriture
# sur secret/apps/* est le backend CNP (ADR-0025).

path "secret/data/apps/*" {
  capabilities = ["read"]
}

# ESO a besoin de lire les métadonnées (versions) pour détecter les mises à
# jour lors de la réconciliation périodique (refreshInterval).
path "secret/metadata/apps/*" {
  capabilities = ["read", "list"]
}
