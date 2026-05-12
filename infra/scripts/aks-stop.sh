#!/bin/bash

set -euo pipefail

RESOURCE_GROUP="cnp-rg"
CLUSTER_NAME="cnp-aks"
NODE_POOL="system"

echo "[CNP] Arrêt du cluster $CLUSTER_NAME (scale a 0)..."
echo "      Les workloads en cours seront perdus."
read -p "Confirmer ? (y/N) : " CONFIRM

if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
  echo "Annulé."
  exit 0
fi

az aks stop --resource-group cnp-rg --name cnp-aks

echo "[CNP] Cluster arrêté. Plus aucun node actif, facturation VMs stoppée."
echo "      Le control plane AKS reste actif."
