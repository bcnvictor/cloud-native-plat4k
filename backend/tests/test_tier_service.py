"""CNP tier helpers live in the service layer (backend.services.tier_service).

Services must not import backend.api.*; deps keeps re-exporting the helpers for the
routes and tests that use them.
"""
import subprocess
import sys

from shared.models import CnpTier


def test_keycloak_service_does_not_import_the_api_deps():
    code = (
        "import sys, backend.services.keycloak_service; "
        "sys.exit(1 if 'backend.api.deps' in sys.modules else 0)"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_deps_reexports_the_service_helpers():
    from backend.api import deps
    from backend.services import tier_service

    assert deps._TIER_ORDER is tier_service.TIER_ORDER
    assert deps._access_level_to_tier is tier_service.access_level_to_tier
    assert deps.get_effective_tier is tier_service.get_effective_tier


def test_tier_helpers():
    from backend.services.tier_service import TIER_ORDER, access_level_to_tier, tier_at_least

    assert TIER_ORDER == [CnpTier.VIEWER, CnpTier.DEVELOPER, CnpTier.MAINTAINER, CnpTier.OWNER]
    assert access_level_to_tier(40) == CnpTier.MAINTAINER
    assert tier_at_least(CnpTier.OWNER, CnpTier.MAINTAINER)
    assert not tier_at_least(CnpTier.DEVELOPER, CnpTier.MAINTAINER)
