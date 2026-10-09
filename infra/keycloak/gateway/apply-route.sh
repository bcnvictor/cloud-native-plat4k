#!/usr/bin/env bash
set -euo pipefail
key=${1:?instance key required}
[[ "$key" =~ ^[a-z0-9]([a-z0-9-]{0,57}[a-z0-9])?$ ]] || exit 2
root=$(cd "$(dirname "$0")/../../.." && pwd)
routes=${CNP_GATEWAY_ROUTES:-$root/infra/keycloak/gateway/generated/routes}
compose=${CNP_GATEWAY_COMPOSE:-$root/docker-compose.yml}
mkdir -p "$routes"
# mkdir provides a portable lock on Linux and macOS. Bound waits, no stale
# lock deletion (another operator may still own it).
for attempt in {1..60}; do
    if mkdir "$routes/.update-lock" 2>/dev/null; then break; fi
    [[ $attempt != 60 ]] || { echo 'Gateway update busy' >&2; exit 1; }
    sleep 1
done
candidate=$(mktemp "$routes/.candidate.XXXXXX")
backup=$(mktemp "$routes/.backup.XXXXXX")
file="$routes/$key.conf"
had_previous=false
if [[ -f "$file" ]]; then cp "$file" "$backup"; had_previous=true; fi
cleanup() { rm -f "$candidate" "$backup"; rmdir "$routes/.update-lock"; }
trap cleanup EXIT
cat > "$candidate"
chmod 644 "$candidate"
args=(-f "$compose")
if [[ -n ${CNP_GATEWAY_PROJECT:-} ]]; then args=(-p "$CNP_GATEWAY_PROJECT" "${args[@]}"); fi
rollback() {
    if $had_previous; then cp "$backup" "$candidate"; mv "$candidate" "$file"; else rm -f "$file"; fi
}
mv "$candidate" "$file"
# The auth virtual host is generated only when its certificate is installed.
if ! docker compose "${args[@]}" exec -T nginx-grafana sh -ec '
    test -n "${AUTH_DOMAIN:-}"
    test -f "/etc/letsencrypt/live/$AUTH_DOMAIN/fullchain.pem"
    envsubst '\''${AUTH_DOMAIN}'\'' < /etc/nginx/auth.conf.template > /etc/nginx/conf.d/auth.conf
    nginx -t
' >/dev/null 2>&1; then
    rollback
    echo 'Gateway configuration rejected; previous route restored' >&2
    exit 1
fi
if ! docker compose "${args[@]}" exec -T nginx-grafana nginx -s reload >/dev/null 2>&1; then
    rollback
    docker compose "${args[@]}" exec -T nginx-grafana nginx -t >/dev/null 2>&1 && docker compose "${args[@]}" exec -T nginx-grafana nginx -s reload >/dev/null 2>&1 || true
    echo 'Gateway reload failed; previous route restored' >&2
    exit 1
fi
