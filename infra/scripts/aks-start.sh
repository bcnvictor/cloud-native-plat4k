#!/bin/bash

set -euo pipefail

RESOURCE_GROUP="cnp-rg"
CLUSTER_NAME="cnp-aks"
NODE_POOL="system"
NODE_COUNT=2

echo "[CNP] Démarrage du cluster $CLUSTER_NAME..."

az aks start --resource-group cnp-rg --name cnp-aks

echo "[CNP] Rafraîchissement du kubeconfig..."
az aks get-credentials --resource-group "$RESOURCE_GROUP" --name "$CLUSTER_NAME" --overwrite-existing

echo "[CNP] Cluster démarré. Nodes actifs :"
kubectl get nodes
