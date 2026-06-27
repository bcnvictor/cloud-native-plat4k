#!/usr/bin/env bash
#
# fetch-kubeconfig.sh — Récupère le kubeconfig du cluster k3s `cnp-k3s` et le réécrit
# pour un accès kubectl DISTANT (depuis le poste / le backend CNP).
#
# Deux modes :
#   A) Exécuté SUR LA VM :    PUBLIC_IP=<ip> ./fetch-kubeconfig.sh
#      -> lit /etc/rancher/k3s/k3s.yaml en local
#   B) Exécuté DEPUIS un poste distant : SSH_HOST=ubuntu@<ip> PUBLIC_IP=<ip> ./fetch-kubeconfig.sh
#      -> récupère le fichier via ssh
#
# Le kubeconfig généré :
#   - pointe l'API server sur https://<PUBLIC_IP>:6443 (au lieu de 127.0.0.1)
#   - renomme le contexte/cluster/user en `cnp-k3s` (= nom de la ClusterConnection CNP,
#     convention attendue par backend/k8s/discovery.py)
#
# Sortie : ./cnp-k3s.yaml  (NE PAS committer — ajouté au .gitignore du dossier)
set -euo pipefail

PUBLIC_IP="${PUBLIC_IP:-}"
SSH_HOST="${SSH_HOST:-}"
SSH_KEY="${SSH_KEY:-}"
OUT="${OUT:-cnp-k3s.yaml}"
CONTEXT_NAME="cnp-k3s"

if [[ -z "${PUBLIC_IP}" ]]; then
  echo "ERREUR : variable PUBLIC_IP requise." >&2
  exit 1
fi

SSH_OPTS=(-o StrictHostKeyChecking=no)
if [[ -n "${SSH_KEY}" ]]; then
  SSH_OPTS+=(-i "${SSH_KEY}")
fi

TMP="$(mktemp)"
trap 'rm -f "${TMP}"' EXIT

if [[ -n "${SSH_HOST}" ]]; then
  echo ">> Récupération du kubeconfig depuis ${SSH_HOST}…"
  ssh "${SSH_OPTS[@]}" "${SSH_HOST}" "sudo cat /etc/rancher/k3s/k3s.yaml" > "${TMP}"
else
  echo ">> Lecture du kubeconfig local /etc/rancher/k3s/k3s.yaml…"
  sudo cat /etc/rancher/k3s/k3s.yaml > "${TMP}"
fi

# Réécriture : endpoint distant + renommage default -> cnp-k3s.
sed -e "s#https://127.0.0.1:6443#https://${PUBLIC_IP}:6443#g" \
    -e "s/: default$/: ${CONTEXT_NAME}/g" \
    -e "s/name: default/name: ${CONTEXT_NAME}/g" \
    "${TMP}" > "${OUT}"

chmod 600 "${OUT}"
echo ">> kubeconfig écrit dans ${OUT} (contexte: ${CONTEXT_NAME})."
echo ">> Test :  KUBECONFIG=${OUT} kubectl --context ${CONTEXT_NAME} get nodes"
