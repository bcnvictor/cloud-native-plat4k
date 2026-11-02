#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
cd "$root"
# Use an explicit full test environment: ordinary operator dependencies do not
# include backend, pytest or browser tooling.
exec "${CNP_TEST_PYTHON:-python}" -m infra.keycloak.tests.smoke "$@"
