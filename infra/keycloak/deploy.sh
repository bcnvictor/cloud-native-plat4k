#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
cd "$root"
exec uv run --no-project --python 3.11 --with-requirements infra/keycloak/requirements.lock \
    python -m infra.keycloak.lib.deploy "$@"
