"""Tests for `cnp env list|set|unset|pull` (4K-248).

The HTTP client is replaced by a recording fake: these tests pin which
endpoints each command calls (notably that `pull` can only ever hit
/env/dev/values) and what ends up on disk.
"""

import stat

import pytest
from typer.testing import CliRunner

from cli.commands import env as env_cmd

runner = CliRunner()

APP_ID = 7
APP_SLUG = "my-app"


class FakeClient:
    def __init__(self, values=None, fail_on_delete=None):
        self.calls: list[tuple] = []
        self.values = values or {}
        self.fail_on_delete = fail_on_delete

    def get(self, endpoint, params=None):
        self.calls.append(("GET", endpoint))
        if endpoint == "/apps/":
            return [{"id": 1, "slug": "other"}, {"id": APP_ID, "slug": APP_SLUG}]
        if endpoint == f"/apps/{APP_ID}/env/dev/values":
            return dict(self.values)
        if endpoint.startswith(f"/apps/{APP_ID}/env/"):
            return {"env": endpoint.rsplit("/", 1)[1], "keys": [{"key": "A", "is_set": True}]}
        raise AssertionError(f"unexpected GET {endpoint}")

    def put(self, endpoint, json=None, data=None):
        self.calls.append(("PUT", endpoint, json))
        return {"env": "dev", "keys": []}

    def delete(self, endpoint):
        self.calls.append(("DELETE", endpoint))
        if self.fail_on_delete and endpoint.endswith(self.fail_on_delete):
            raise Exception("Error: Vault unavailable")
        return {"msg": "Variable deleted"}

    def endpoints(self, method=None):
        return [c[1] for c in self.calls if method is None or c[0] == method]


@pytest.fixture
def fake_client(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(env_cmd, "client", fake)
    return fake


def _invoke(*args):
    return runner.invoke(env_cmd.app, list(args))


class TestList:
    @pytest.mark.parametrize("env", ["dev", "prod"])
    def test_list_calls_keys_endpoint(self, fake_client, env):
        result = _invoke("list", "-a", APP_SLUG, "-e", env)
        assert result.exit_code == 0, result.output
        assert fake_client.endpoints() == ["/apps/", f"/apps/{APP_ID}/env/{env}"]
        assert "A" in result.output

    def test_list_rejects_unknown_env_without_calling_api(self, fake_client):
        result = _invoke("list", "-a", APP_SLUG, "-e", "staging")
        assert result.exit_code == 1
        assert fake_client.calls == []

    def test_list_unknown_slug(self, fake_client):
        result = _invoke("list", "-a", "nope", "-e", "dev")
        assert result.exit_code == 1
        assert "nope" in result.output
        assert fake_client.endpoints() == ["/apps/"]


class TestSet:
    def test_multiple_pairs_single_put(self, fake_client):
        result = _invoke("set", "-a", APP_SLUG, "-e", "prod", "A=1", "B=two words", "C=x=y")
        assert result.exit_code == 0, result.output
        puts = [c for c in fake_client.calls if c[0] == "PUT"]
        assert puts == [("PUT", f"/apps/{APP_ID}/env/prod", {"variables": {"A": "1", "B": "two words", "C": "x=y"}})]

    def test_pair_without_equals_rejected_before_any_call(self, fake_client):
        result = _invoke("set", "-a", APP_SLUG, "-e", "dev", "A=1", "BROKEN")
        assert result.exit_code == 1
        assert fake_client.calls == []

    def test_unknown_env_rejected(self, fake_client):
        result = _invoke("set", "-a", APP_SLUG, "-e", "PROD", "A=1")
        assert result.exit_code == 1
        assert fake_client.calls == []

    def test_unknown_slug_no_put(self, fake_client):
        result = _invoke("set", "-a", "nope", "-e", "dev", "A=1")
        assert result.exit_code == 1
        assert fake_client.endpoints("PUT") == []


class TestUnset:
    def test_one_delete_per_key(self, fake_client):
        result = _invoke("unset", "-a", APP_SLUG, "-e", "dev", "A", "B")
        assert result.exit_code == 0, result.output
        assert fake_client.endpoints("DELETE") == [
            f"/apps/{APP_ID}/env/dev/A",
            f"/apps/{APP_ID}/env/dev/B",
        ]

    def test_keys_are_url_encoded(self, fake_client):
        """A key containing URL metacharacters must stay one path segment
        (the web UI already encodes it, apps.ts deleteEnvVar)."""
        result = _invoke("unset", "-a", APP_SLUG, "-e", "dev", "A#B", "C?D", "E/F")
        assert result.exit_code == 0, result.output
        assert fake_client.endpoints("DELETE") == [
            f"/apps/{APP_ID}/env/dev/A%23B",
            f"/apps/{APP_ID}/env/dev/C%3FD",
            f"/apps/{APP_ID}/env/dev/E%2FF",
        ]

    def test_partial_failure_reports_what_was_removed(self, monkeypatch):
        fake = FakeClient(fail_on_delete="/B")
        monkeypatch.setattr(env_cmd, "client", fake)
        result = _invoke("unset", "-a", APP_SLUG, "-e", "dev", "A", "B", "C")
        assert result.exit_code == 1
        # Every key is attempted, and the user is told exactly which ones changed.
        assert fake.endpoints("DELETE") == [
            f"/apps/{APP_ID}/env/dev/A",
            f"/apps/{APP_ID}/env/dev/B",
            f"/apps/{APP_ID}/env/dev/C",
        ]
        assert "Removed 3" not in result.output
        assert "A" in result.output and "C" in result.output
        assert "B" in result.output and "Vault unavailable" in result.output


class TestPullDevLock:
    @pytest.mark.parametrize("env", ["prod", "PROD", "staging", "Dev", ""])
    def test_pull_refuses_anything_but_dev_without_calling_api(self, fake_client, tmp_path, env):
        out = tmp_path / ".env.local"
        result = _invoke("pull", "-a", APP_SLUG, "-e", env, "-o", str(out))
        assert result.exit_code == 1
        assert fake_client.calls == []
        assert not out.exists()

    def test_pull_only_hits_dev_values(self, monkeypatch, tmp_path):
        fake = FakeClient(values={"A": "1"})
        monkeypatch.setattr(env_cmd, "client", fake)
        out = tmp_path / ".env.local"
        result = _invoke("pull", "-a", APP_SLUG, "-o", str(out))
        assert result.exit_code == 0, result.output
        assert fake.endpoints() == ["/apps/", f"/apps/{APP_ID}/env/dev/values"]


class TestPullFile:
    TRICKY = {
        "PLAIN": "value",
        "SPACES": "two words",
        "HASH": "abc#def",
        "QUOTES": "it's \"quoted\"",
        "DOLLAR": "pa$$word${HOME}",
        "BACKSLASH": "C:\\path\\n",
        "DOUBLE_BACKSLASH": "a\\\\b",
        "TRAILING_BACKSLASH": "end\\",
        "BACKSLASH_QUOTE": "x\\'y",
        "MULTILINE": "-----BEGIN KEY-----\nline2\n-----END KEY-----",
        "EQUALS": "a=b",
        "EMPTY": "",
    }

    def _pull(self, monkeypatch, out, *extra):
        fake = FakeClient(values=self.TRICKY)
        monkeypatch.setattr(env_cmd, "client", fake)
        return _invoke("pull", "-a", APP_SLUG, "-o", str(out), *extra)

    def test_values_round_trip_through_dotenv(self, monkeypatch, tmp_path):
        dotenv = pytest.importorskip("dotenv")
        out = tmp_path / ".env.local"
        result = self._pull(monkeypatch, out)
        assert result.exit_code == 0, result.output
        # interpolate=False: python-dotenv expands ${VAR} even inside single
        # quotes and has no escape for it, so no file format can keep ${HOME}
        # literal for its default mode. Single quotes are literal for Docker
        # Compose and Node dotenv; here we check the raw parse round-trips.
        assert dotenv.dotenv_values(out, interpolate=False) == self.TRICKY

    def test_file_is_owner_only(self, monkeypatch, tmp_path):
        out = tmp_path / ".env.local"
        result = self._pull(monkeypatch, out)
        assert result.exit_code == 0, result.output
        assert stat.S_IMODE(out.stat().st_mode) == 0o600

    def test_existing_file_not_overwritten_without_force(self, monkeypatch, tmp_path):
        out = tmp_path / ".env.local"
        out.write_text("LOCAL_ONLY=keep-me\n")
        result = self._pull(monkeypatch, out)
        assert result.exit_code == 1
        assert out.read_text() == "LOCAL_ONLY=keep-me\n"

    def test_force_overwrites_and_tightens_permissions(self, monkeypatch, tmp_path):
        out = tmp_path / ".env.local"
        out.write_text("OLD=1\n")
        out.chmod(0o644)
        result = self._pull(monkeypatch, out, "--force")
        assert result.exit_code == 0, result.output
        assert "OLD" not in out.read_text()
        assert stat.S_IMODE(out.stat().st_mode) == 0o600
