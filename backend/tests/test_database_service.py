from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from shared.models import ScaffoldingParams

from backend.services import database_service
from backend.services.database_service import build_db_credentials, provision_database_secrets

BASE = "apps/4k-cnp-2027/cnp-apps/booking/shop"


async def _provision(params: ScaffoldingParams, vault: MagicMock):
    with patch.object(database_service, "vault_client", vault):
        return await provision_database_secrets(
            group_slug="4k-cnp-2027/cnp-apps/booking", app_slug="shop", app_name="shop", params=params,
        )


async def test_generated_passwords_differ_between_dev_and_prod():
    vault = MagicMock()
    await _provision(ScaffoldingParams(services=["postgresql"]), vault)

    written = {c.args[0]: c.args[1] for c in vault.patch_secret.call_args_list}
    assert set(written) == {f"{BASE}/dev", f"{BASE}/prod"}
    dev, prod = written[f"{BASE}/dev"], written[f"{BASE}/prod"]
    assert dev["POSTGRES_PASSWORD"] != prod["POSTGRES_PASSWORD"]
    assert len(dev["POSTGRES_PASSWORD"]) >= 24
    assert dev["DATABASE_URL"] == f"postgresql://appuser:{dev['POSTGRES_PASSWORD']}@shop-postgresql:5432/shop"


async def test_chosen_password_and_name_are_used_for_both_envs():
    vault = MagicMock()
    await _provision(ScaffoldingParams(services=["postgresql"], db_name="orders", db_password="s3cret/pass@word"), vault)

    for call in vault.patch_secret.call_args_list:
        creds = call.args[1]
        assert creds["POSTGRES_PASSWORD"] == "s3cret/pass@word"
        assert creds["POSTGRES_DB"] == "orders"
        # Caractères réservés d'URL encodés dans DATABASE_URL.
        assert creds["DATABASE_URL"] == "postgresql://appuser:s3cret%2Fpass%40word@shop-postgresql:5432/orders"


async def test_vault_failure_aborts_with_503():
    vault = MagicMock()
    vault.patch_secret.side_effect = RuntimeError("sealed")
    with pytest.raises(HTTPException) as exc:
        await _provision(ScaffoldingParams(services=["postgresql"]), vault)
    assert exc.value.status_code == 503


def test_credentials_keys_are_the_managed_ones():
    assert set(build_db_credentials("shop", "shop", "x" * 12)) == database_service.DB_MANAGED_KEYS


@pytest.mark.parametrize("params", [
    {"db_password": "short"},
    {"db_name": "Bad-Name"},
    {"pg_size": "5GB"},
])
def test_invalid_database_settings_are_rejected(params):
    with pytest.raises(ValidationError):
        ScaffoldingParams(services=["postgresql"], **params)


def test_password_is_masked_in_repr():
    params = ScaffoldingParams(services=["postgresql"], db_password="correct-horse-battery")
    assert "correct-horse-battery" not in repr(params)
