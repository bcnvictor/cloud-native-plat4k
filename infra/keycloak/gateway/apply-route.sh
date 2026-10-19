#!/usr/bin/env bash
set -euo pipefail
key=${1:?instance key required}
action=${2:-apply}
transaction=${3:-}
[[ "$key" =~ ^[a-z0-9]([a-z0-9-]{0,57}[a-z0-9])?$ ]] || exit 2
[[ "$action" == apply || "$action" == stage || "$action" == commit || "$action" == rollback ]] || exit 2
if [[ "$action" != apply ]]; then [[ "$transaction" =~ ^[a-f0-9]{32}$ ]] || exit 2; fi
root=$(cd "$(dirname "$0")/../../.." && pwd)
routes=${CNP_GATEWAY_ROUTES:-$root/infra/keycloak/gateway/generated/routes}
compose=${CNP_GATEWAY_COMPOSE:-$root/docker-compose.yml}
mkdir -p "$routes"
lock="$routes/.update-lock"
file="$routes/$key.conf"
args=(-f "$compose")
if [[ -n ${CNP_GATEWAY_PROJECT:-} ]]; then args=(-p "$CNP_GATEWAY_PROJECT" "${args[@]}"); fi
nginx_check() {
    docker compose "${args[@]}" exec -T nginx-grafana sh -ec '
        test -n "${AUTH_DOMAIN:-}"
        test -f "/etc/letsencrypt/live/$AUTH_DOMAIN/fullchain.pem"
        envsubst '\''${AUTH_DOMAIN}'\'' < /etc/nginx/auth.conf.template > /etc/nginx/conf.d/auth.conf
        nginx -t
    ' >/dev/null 2>&1
}
nginx_reload() { docker compose "${args[@]}" exec -T nginx-grafana nginx -s reload >/dev/null 2>&1; }
cleanup() { rm -f "$lock/previous.conf" "$lock/candidate.conf" "$lock/owner" "$lock/key" "$lock/had_previous"; rmdir "$lock"; }
restore() {
    if [[ $(cat "$lock/had_previous") == true ]]; then
        cp "$lock/previous.conf" "$lock/candidate.conf"
        mv "$lock/candidate.conf" "$file"
    else
        rm -f "$file"
    fi
}
if [[ "$action" == commit || "$action" == rollback ]]; then
    # Only the transaction which staged this route may release or undo it.
    [[ -f "$lock/owner" && $(cat "$lock/owner") == "$transaction" && $(cat "$lock/key") == "$key" ]] || { echo 'Gateway transaction ownership mismatch' >&2; exit 1; }
    if [[ "$action" == rollback ]]; then
        restore
        if ! nginx_check || ! nginx_reload; then
            echo 'Gateway rollback incomplete; transaction retained for retry' >&2
            exit 1
        fi
    fi
    cleanup
    exit 0
fi
# Keep this lock until the caller has verified public discovery and activated
# CNP. A crashed operator leaves a recoverable transaction, never an automatic
# unlock that could race a still-running update.
for attempt in {1..60}; do
    if mkdir "$lock" 2>/dev/null; then break; fi
    [[ $attempt != 60 ]] || { echo 'Gateway update busy' >&2; exit 1; }
    sleep 1
done
printf '%s' "${transaction:-apply}" > "$lock/owner"
printf '%s' "$key" > "$lock/key"
if [[ -f "$file" ]]; then
    cp "$file" "$lock/previous.conf"
    printf true > "$lock/had_previous"
else
    printf false > "$lock/had_previous"
fi
keep_lock=false
trap 'if ! $keep_lock; then cleanup; fi' EXIT
cat > "$lock/candidate.conf"
chmod 644 "$lock/candidate.conf"
mv "$lock/candidate.conf" "$file"
if ! nginx_check || ! nginx_reload; then
    restore
    if ! nginx_check || ! nginx_reload; then
        keep_lock=true
        echo 'Gateway rollback incomplete; transaction retained for retry' >&2
    fi
    echo 'Gateway candidate rejected; previous route restored' >&2
    exit 1
fi
if [[ "$action" == stage ]]; then keep_lock=true; fi
