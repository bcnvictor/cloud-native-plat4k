"""CAS-only credential creation and dedicated Vault identities."""

from pathlib import Path
from urllib.parse import quote

from .http_api import JSONAPI, APIError


class VaultAPI(JSONAPI):
    def __init__(self, url, token):
        super().__init__(url, {"X-Vault-Token": token})

    def ensure_secret(self, path: str, initial: dict[str, str]) -> dict[str, str]:
        api_path = "/v1/secret/data/" + quote(path, safe="/")
        existing = self.request("GET", api_path, missing_ok=True)
        if existing is not None:
            return existing["data"]["data"]
        try:
            self.request("POST", api_path, {"options": {"cas": 0}, "data": initial})
            return initial
        except APIError as exc:
            if exc.status not in (400, 409):
                raise
            winner = self.request("GET", api_path, missing_ok=True)
            if winner is None:
                raise RuntimeError("Vault secret creation failed") from None
            return winner["data"]["data"]

    def ensure_eso_token(self, instance_key: str) -> str:
        template = Path(__file__).resolve().parents[1] / "vault/keycloak-eso-reader.hcl.template"
        policy = f"keycloak-eso-{instance_key}"
        self.request(
            "PUT",
            f"/v1/sys/policies/acl/{policy}",
            {"policy": template.read_text().replace("{{instance_key}}", instance_key)},
        )
        path = f"cnp/keycloak/{instance_key}/eso-token"
        existing = self.request("GET", f"/v1/secret/data/{path}", missing_ok=True)
        if existing:
            token = existing["data"]["data"]["token"]
            scoped = VaultAPI(self.url, token)
            scoped.request("POST", "/v1/auth/token/renew-self", {})
            return token
        # Periodic token; renew on every deployment and via the dedicated renewer.
        created = self.request(
            "POST",
            "/v1/auth/token/create",
            {"policies": [policy], "period": "720h", "no_parent": True, "no_default_policy": True},
        )
        token = created["auth"]["client_token"]
        winner = self.ensure_secret(path, {"token": token})["token"]
        if winner != token:
            VaultAPI(self.url, token).request("POST", "/v1/auth/token/revoke-self", {})
        return winner

    def store_provisioner(self, instance_key: str, secret: str) -> None:
        existing = self.ensure_secret(
            f"cnp/keycloak/{instance_key}/provisioner", {"client_secret": secret}
        )
        if existing.get("client_secret") != secret:
            raise RuntimeError("Existing provisioner credential is different; refusing rotation")

    def extend_backend_policy(self, instance_key: str, name="cnp-backend"):
        existing = self.request("GET", f"/v1/sys/policies/acl/{quote(name, safe='')}")
        original = existing["data"]["policy"]
        path = "secret/data/cnp/keycloak/+/provisioner"
        # Preserve every existing rule. Read additions do not grant app-token access.
        if f'path "{path}"' not in original:
            addition = (
                (Path(__file__).resolve().parents[1] / "vault/cnp-keycloak-reader.hcl.template")
                .read_text()
                .replace("{{instance_key}}", "+")
            )
            self.request(
                "PUT",
                f"/v1/sys/policies/acl/{quote(name, safe='')}",
                {"policy": original + "\n" + addition},
            )
