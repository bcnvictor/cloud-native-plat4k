#!/usr/bin/env bash
#
# install-k3s.sh — Installe k3s single-node sur la VM Oracle `cnp-k3s`.
#
# Cloud privé du sujet multi-cloud (4K-45) : k8s auto-géré (pas de service managé).
# Cible : VM Ampere A1 (aarch64), 3 OCPU / 20 GB, Ubuntu. À exécuter EN SSH SUR LA VM.
#
# Usage :
#   PUBLIC_IP=<ip_publique_vm> ./install-k3s.sh
#
# Ce que fait le script :
#   - installe k3s (control plane léger) en désactivant traefik (CNP gère son ingress)
#   - ajoute l'IP publique au certificat de l'API server (--tls-san) pour kubectl distant
#   - ouvre le port 6443 dans le firewall local de la VM (iptables, persistant Oracle)
#
# ⚠️ Le port 6443 doit AUSSI être ouvert côté OCI : voir README.md (security list / NSG).
set -euo pipefail

PUBLIC_IP="${PUBLIC_IP:-}"
if [[ -z "${PUBLIC_IP}" ]]; then
  echo "ERREUR : variable PUBLIC_IP requise (IP publique de la VM cnp-k3s)." >&2
  echo "  ex: PUBLIC_IP=140.238.x.x ./install-k3s.sh" >&2
  exit 1
fi

echo ">> Installation de k3s (tls-san=${PUBLIC_IP}, traefik désactivé)…"
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server \
  --disable traefik \
  --write-kubeconfig-mode 644 \
  --tls-san ${PUBLIC_IP}" sh -

echo ">> Attente de la disponibilité du node…"
until sudo k3s kubectl get nodes 2>/dev/null | grep -q ' Ready'; do
  sleep 3
done
sudo k3s kubectl get nodes -o wide

# Oracle Linux/Ubuntu sur OCI applique des règles iptables restrictives par défaut.
# On autorise explicitement le port de l'API server k3s.
echo ">> Ouverture du port 6443 dans le firewall local de la VM…"
if command -v iptables >/dev/null 2>&1; then
  sudo iptables -I INPUT -p tcp --dport 6443 -j ACCEPT || true
  # Persistance (Ubuntu : netfilter-persistent ; sinon, à reporter dans votre conf).
  if command -v netfilter-persistent >/dev/null 2>&1; then
    sudo netfilter-persistent save || true
  fi
fi

echo
echo ">> k3s installé. Étapes suivantes :"
echo "   1. Ouvrir le port 6443 côté OCI (security list / NSG) — cf. README.md"
echo "   2. Récupérer le kubeconfig :  PUBLIC_IP=${PUBLIC_IP} ./fetch-kubeconfig.sh"
