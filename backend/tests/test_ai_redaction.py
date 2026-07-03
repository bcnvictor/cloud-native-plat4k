from backend.ai.redaction import RedactionResult, redact


# --- Helper ---

def _assert_redacted(text: str, label: str, absent: str) -> RedactionResult:
    result = redact(text)
    assert absent not in result.text, f"Expected '{absent}' to be redacted"
    assert label in result.labels, f"Expected label '{label}' in {result.labels}"
    return result


# --- GitLab tokens ---

def test_redact_gitlab_pat():
    _assert_redacted(
        "Token: glpat-abcdefghij1234567890",
        "gitlab-token",
        "glpat-abcdefghij1234567890",
    )


def test_redact_gitlab_ci_token():
    _assert_redacted(
        "CI_TOKEN=glcbt-xyz0987654321abcdef",
        "gitlab-token",
        "glcbt-xyz0987654321abcdef",
    )


# --- JWT ---

def test_redact_jwt():
    jwt = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        ".eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ"
        ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    result = _assert_redacted(f"token: {jwt}", "jwt", "eyJhbGci")
    assert "[REDACTED:jwt]" in result.text


# --- Vault tokens ---

def test_redact_vault_hvs_token():
    _assert_redacted(
        "VAULT_TOKEN=hvs.AAAAAQIhALN4T8buvnJq2ysIqJBv7oI123456789",
        "vault-token",
        "hvs.AAAAAQIhALN4T8buvnJq2ysIqJBv7oI123456789",
    )


def test_redact_vault_legacy_token():
    _assert_redacted(
        "token: s.abcdefghijklmnopqrstuvwxyz12",
        "vault-token",
        "s.abcdefghijklmnopqrstuvwxyz12",
    )


# --- Bearer tokens ---

def test_redact_bearer_token_value_removed():
    result = redact("Authorization: Bearer supersecrettoken12345678")
    assert "supersecrettoken12345678" not in result.text
    assert "bearer-token" in result.labels


def test_redact_bearer_keeps_keyword():
    result = redact("Authorization: Bearer supersecrettoken12345678")
    assert "Bearer" in result.text


def test_redact_bearer_case_insensitive():
    result = redact("authorization: bearer supersecrettoken12345678")
    assert "supersecrettoken12345678" not in result.text
    assert "bearer-token" in result.labels


# --- Private keys ---

def test_redact_rsa_private_key():
    key = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA12345secret\n"
        "-----END RSA PRIVATE KEY-----"
    )
    result = _assert_redacted(key, "private-key", "MIIEowIBAAKCAQEA12345secret")
    assert "[REDACTED:private-key]" in result.text


def test_redact_generic_private_key():
    key = (
        "-----BEGIN PRIVATE KEY-----\n"
        "MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSk\n"
        "-----END PRIVATE KEY-----"
    )
    _assert_redacted(key, "private-key", "MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSk")


# --- Connection strings ---

def test_redact_postgres_connection_string():
    _assert_redacted(
        "DB_URL=postgresql://admin:p@ssw0rd!@db.internal:5432/cnp",
        "connection-string",
        "p@ssw0rd!",
    )


def test_redact_redis_connection_string():
    _assert_redacted(
        "REDIS_URL=redis://default:verysecret@redis.internal:6379/0",
        "connection-string",
        "verysecret",
    )


# --- ArgoCD tokens ---

def test_redact_argocd_token():
    _assert_redacted(
        "ARGOCD_TOKEN=argocd_abcdefghij1234567890abcd",
        "argocd-token",
        "argocd_abcdefghij1234567890abcd",
    )


# --- Clean text — no false positives ---

def test_clean_text_unchanged():
    text = "App prod-eu-west-1 has 3 replicas. Status: healthy. Cost: $12.50/day."
    result = redact(text)
    assert result.text == text
    assert result.labels == []


def test_url_without_credentials_not_redacted():
    text = "Endpoint: https://api.deepseek.com/chat/completions"
    result = redact(text)
    assert result.text == text
    assert result.labels == []


def test_short_bearer_not_redacted():
    # Tokens under 8 chars should not trigger (too short to be real tokens)
    text = "Authorization: Bearer abc123"
    result = redact(text)
    assert "bearer-token" not in result.labels


# --- Multiple secrets in one text ---

def test_multiple_secrets():
    text = (
        "token=glpat-abcdefghij1234567890\n"
        "db=postgresql://user:secretpass@host/db\n"
    )
    result = redact(text)
    assert "glpat-" not in result.text
    assert "secretpass" not in result.text
    assert set(result.labels) == {"gitlab-token", "connection-string"}


def test_duplicate_pattern_label_deduplicated():
    text = "glpat-abcdefghij1234567890 and glpat-zyxwvutsrq0987654321"
    result = redact(text)
    assert result.labels.count("gitlab-token") == 1


# --- Return type ---

def test_returns_named_tuple():
    result = redact("clean text")
    assert isinstance(result, RedactionResult)
    assert isinstance(result.text, str)
    assert isinstance(result.labels, list)
