#!/usr/bin/env bash
# Record the current ClusterIPs of Prometheus and Loki so they can be
# pinned in their Helm values before any accidental service recreation.
#
# Run once when the cluster is up:
#   bash infra/aks/monitoring/pin-clusterips.sh
#
# Then update PROMETHEUS_URL / LOKI_URL in cnp-control's .env with the output.
set -euo pipefail

NAMESPACE="monitoring"

PROM_IP=$(kubectl get svc -n "$NAMESPACE" kube-prometheus-stack-prometheus \
  -o jsonpath='{.spec.clusterIP}' 2>/dev/null || echo "NOT_FOUND")

LOKI_IP=$(kubectl get svc -n "$NAMESPACE" loki \
  -o jsonpath='{.spec.clusterIP}' 2>/dev/null || echo "NOT_FOUND")

echo "Prometheus ClusterIP : $PROM_IP  → PROMETHEUS_URL=http://${PROM_IP}:9090"
echo "Loki ClusterIP       : $LOKI_IP  → LOKI_URL=http://${LOKI_IP}:3100"
echo ""
echo "Add to /etc/environment or cnp-control .env on the Oracle VM:"
echo "  PROMETHEUS_URL=http://${PROM_IP}:9090"
echo "  LOKI_URL=http://${LOKI_IP}:3100"
echo ""
echo "To pin Prometheus ClusterIP in kube-prometheus-stack values:"
echo "  prometheus.service.clusterIP: \"${PROM_IP}\""
echo "To pin Loki ClusterIP in loki-stack values:"
echo "  loki.service.clusterIP: \"${LOKI_IP}\""
