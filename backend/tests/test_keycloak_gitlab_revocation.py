from backend.services.gitlab_sync_service import _maybe_revoke_keycloak_access
from backend.services.keycloak_service import KeycloakService
from backend.tests.test_keycloak_instance_routing import providers as provider_fixture

providers = provider_fixture


async def test_gitlab_revocation_uses_bound_instance(providers, db_session, admin_user):
    app, _, fakes, _ = providers
    fake = fakes["private-01"]
    fake.create_realm("commande-prod", {"cnp_app_id": str(app.id)})
    await KeycloakService(db_session).grant_console_access(app, "prod", admin_user)
    await _maybe_revoke_keycloak_access(db_session, app, admin_user.id)
    assert fake.realms["commande-prod"]["users"] == {}
