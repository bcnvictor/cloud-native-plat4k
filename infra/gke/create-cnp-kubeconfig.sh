#!/usr/bin/env bash
#
# create-cnp-kubeconfig.sh — Génère un kubeconfig STATIQUE pour le cluster GKE `cnp-gke`,
# utilisable par le backend CNP (health-worker, déploiements routés par cluster_id).
#
# Pourquoi : le kubeconfig produit par `gcloud container clusters get-credentials`
# s'authentifie via le plugin exec `gke-gcloud-auth-plugin`, absent du conteneur backend.
# Stocké tel quel dans Vault, le cluster resterait OFFLINE. On crée donc un ServiceAccount
# Kubernetes dédié avec un token longue durée, et un kubeconfig qui l'embarque.
#
# Prérequis : kubectl pointant sur le cluster GKE (après get-credentials, cf. README).
#   CONTEXT=<contexte gke> ./create-cnp-kubeconfig.sh   (défaut : contexte courant)
#
# Sortie : ./cnp-gke.yaml  (NE PAS committer — ajouté au .gitignore du dossier)
set -euo pipefail

CONTEXT="${CONTEXT:-$(kubectl config current-context)}"
OUT="${OUT:-cnp-gke.yaml}"
NAME="cnp-gke"
SA="cnp-backend"
NS="kube-system"

k() { kubectl --context "${CONTEXT}" "$@"; }

echo ">> Contexte source : ${CONTEXT}"

# ServiceAccount + droits cluster-admin : mêmes droits que le certificat masterclient
# d'AKS et le kubeconfig admin de k3s (CNP crée namespaces, deployments, services…)
k apply -f - <<EOF
apiVersion: v1
kind: ServiceAccount
metadata:
  name: ${SA}
  namespace: ${NS}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: ${SA}-cluster-admin
subjects:
  - kind: ServiceAccount
    name: ${SA}
    namespace: ${NS}
roleRef:
  kind: ClusterRole
  name: cluster-admin
  apiGroup: rbac.authorization.k8s.io
---
# Token non expirant lié au ServiceAccount (révocable en supprimant ce Secret)
apiVersion: v1
kind: Secret
metadata:
  name: ${SA}-token
  namespace: ${NS}
  annotations:
    kubernetes.io/service-account.name: ${SA}
type: kubernetes.io/service-account-token
EOF

echo ">> Attente du token…"
TOKEN=""
for _ in $(seq 1 30); do
  TOKEN="$(k -n "${NS}" get secret "${SA}-token" -o jsonpath='{.data.token}' 2>/dev/null | base64 -d || true)"
  [[ -n "${TOKEN}" ]] && break
  sleep 1
done
[[ -n "${TOKEN}" ]] || { echo "ERREUR : token du ServiceAccount non généré." >&2; exit 1; }

SERVER="$(k config view --raw --minify -o jsonpath='{.clusters[0].cluster.server}')"
CA="$(k -n "${NS}" get secret "${SA}-token" -o jsonpath='{.data.ca\.crt}')"

umask 077
cat > "${OUT}" <<EOF
apiVersion: v1
kind: Config
clusters:
  - name: ${NAME}
    cluster:
      server: ${SERVER}
      certificate-authority-data: ${CA}
users:
  - name: ${NAME}
    user:
      token: ${TOKEN}
contexts:
  - name: ${NAME}
    context:
      cluster: ${NAME}
      user: ${NAME}
current-context: ${NAME}
EOF
unset TOKEN

echo ">> Vérification du kubeconfig statique…"
kubectl --kubeconfig "${OUT}" get ns >/dev/null
echo ">> kubeconfig écrit dans ${OUT} (contexte: ${NAME}, server: ${SERVER})."
