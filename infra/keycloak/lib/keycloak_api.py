"""Idempotent bootstrap through a private, temporary port-forward."""

import secrets
from urllib.parse import quote

from .http_api import JSONAPI, APIError


class KeycloakAdmin(JSONAPI):
    def __init__(self, url, username, password):
        super().__init__(url)
        self.username = username
        self.password = password
        self.login()

    def login(self):
        self.headers = {}
        token = self.request(
            "POST",
            "/realms/master/protocol/openid-connect/token",
            {
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": self.username,
                "password": self.password,
            },
            form=True,
        )
        self.headers = {"Authorization": "Bearer " + token["access_token"]}

    def ensure_provisioner(self, client_id: str = "cnp-provisioner") -> str:
        clients = self.request(
            "GET", "/admin/realms/master/clients?clientId=" + quote(client_id, safe="")
        )
        if not clients:
            try:
                self.request(
                    "POST",
                    "/admin/realms/master/clients",
                    {
                        "clientId": client_id,
                        "protocol": "openid-connect",
                        "publicClient": False,
                        "serviceAccountsEnabled": True,
                        "standardFlowEnabled": False,
                        "directAccessGrantsEnabled": False,
                        "enabled": True,
                    },
                )
            except APIError as exc:
                if exc.status != 409:
                    raise
            clients = self.request(
                "GET", "/admin/realms/master/clients?clientId=" + quote(client_id, safe="")
            )
        client = clients[0]
        if client.get("publicClient") or not client.get("serviceAccountsEnabled"):
            raise RuntimeError("Existing provisioner client is incompatible")
        internal = client["id"]
        account = self.request(
            "GET", f"/admin/realms/master/clients/{internal}/service-account-user"
        )
        role = self.request("GET", "/admin/realms/master/roles/admin")
        self.request(
            "POST", f"/admin/realms/master/users/{account['id']}/role-mappings/realm", [role]
        )
        return self.request("GET", f"/admin/realms/master/clients/{internal}/client-secret")[
            "value"
        ]

    def verify_public_issuer(self, public_url: str) -> None:
        realm = "cnp-bootstrap-" + secrets.token_hex(8)
        owner = secrets.token_hex(16)
        self.request(
            "POST",
            "/admin/realms",
            {"realm": realm, "enabled": True, "attributes": {"cnp.bootstrap.owner": owner}},
        )
        self.login()  # New realm permissions require a newly issued master token.
        try:
            discovery = JSONAPI(public_url).request(
                "GET", f"/realms/{realm}/.well-known/openid-configuration"
            )
            expected = public_url.rstrip("/") + "/realms/" + realm
            if discovery.get("issuer") != expected or any(
                not discovery.get(field, "").startswith(expected + "/")
                for field in ("authorization_endpoint", "token_endpoint", "jwks_uri")
            ):
                raise RuntimeError("Public issuer does not match configured instance")
        finally:
            existing = self.request("GET", f"/admin/realms/{realm}", missing_ok=True)
            if existing and existing.get("attributes", {}).get("cnp.bootstrap.owner") == owner:
                self.request("DELETE", f"/admin/realms/{realm}")
