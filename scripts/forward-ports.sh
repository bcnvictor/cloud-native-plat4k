#!/usr/bin/env bash
# Usage: ./scripts/pf.sh [start|stop|status]
#   start  (défaut) — lance les port-forwards manquants, ignore ceux déjà actifs
#   stop             — tue tous les port-forwards gérés par ce script
#   status           — affiche l'état de chaque port
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; RESET='\033[0m'
info() { echo -e "${GREEN}[PF]${RESET} $*"; }
warn() { echo -e "${YELLOW}[PF]${RESET} $*"; }

port_bound() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti:"$1" >/dev/null 2>&1
  else
    ss -tlnp 2>/dev/null | grep -q ":$1 "
  fi
}

start_pf() {
  local name="$1" port="$2"; shift 2
  if port_bound "$port"; then
    warn "$name : port $port déjà occupé — ignoré"
  else
    kubectl "$@" >/dev/null 2>&1 &
    info "$name → localhost:$port (PID $!)"
  fi
}

stop_pf() {
  local name="$1" port="$2"
  local pids
  pids=$(lsof -ti:"$port" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null && info "$name (port $port) arrêté" || warn "$name : impossible de tuer $pids"
  else
    warn "$name : port $port non occupé"
  fi
}

status_pf() {
  local name="$1" port="$2" url="$3"
  if port_bound "$port"; then
    echo -e "  ${GREEN}✓${RESET} $name  $url"
  else
    echo -e "  ${RED}✗${RESET} $name  $url"
  fi
}

CMD="${1:-start}"

case "$CMD" in
  start)
    info "Démarrage des port-forwards..."
    start_pf "prometheus"  9090  port-forward -n monitoring svc/prometheus-operated            9090:9090 --address 0.0.0.0
    start_pf "loki"        3100  port-forward -n monitoring svc/loki                           3100:3100 --address 0.0.0.0
    start_pf "grafana"     3000  port-forward -n monitoring svc/kube-prometheus-stack-grafana  3000:80
    start_pf "argocd"      8080  port-forward -n argocd      svc/argocd-server                 8080:443
    echo ""
    info "Endpoints :"
    echo -e "  Prometheus : http://localhost:9090"
    echo -e "  Loki       : http://localhost:3100"
    echo -e "  Grafana    : http://localhost:3000"
    echo -e "  ArgoCD     : https://localhost:8080"
    ;;
  stop)
    info "Arrêt des port-forwards..."
    stop_pf "prometheus"  9090
    stop_pf "loki"        3100
    stop_pf "grafana"     3000
    stop_pf "argocd"      8080
    ;;
  status)
    info "État des port-forwards :"
    status_pf "prometheus"  9090  "http://localhost:9090"
    status_pf "loki"        3100  "http://localhost:3100"
    status_pf "grafana"     3000  "http://localhost:3000"
    status_pf "argocd"      8080  "https://localhost:8080"
    ;;
  *)
    echo -e "${RED}Usage :${RESET} $0 [start|stop|status]"
    exit 1
    ;;
esac
