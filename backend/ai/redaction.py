"""Redact secrets and credentials from text before sending to an LLM.

All content passed to an LLM provider MUST go through redact() first.
Tests must cover every pattern type; see backend/tests/test_ai_redaction.py.
"""

import re
from typing import NamedTuple

# (label, compiled_pattern, replacement_string)
_RULES: list[tuple[str, re.Pattern, str]] = [
    # GitLab personal/CI/deploy/other tokens
    (
        "gitlab-token",
        re.compile(r"gl(?:pat|cbt|dt|oit|prt|sst|rt)-[\w\-]{10,}"),
        "[REDACTED:gitlab-token]",
    ),
    # JWT — header.payload.signature (all base64url segments start with eyJ)
    (
        "jwt",
        re.compile(
            r"eyJ[A-Za-z0-9+/\-_]+\.eyJ[A-Za-z0-9+/\-_]+\.[A-Za-z0-9+/\-_=]+"
        ),
        "[REDACTED:jwt]",
    ),
    # Vault tokens (hvs.xxx — new format; s.xxx — legacy)
    (
        "vault-token",
        re.compile(r"\b(?:hvs|s)\.[\w]{20,}\b"),
        "[REDACTED:vault-token]",
    ),
    # HTTP Bearer tokens — preserve the "Bearer" keyword, redact the value
    (
        "bearer-token",
        re.compile(r"(?i)\bBearer\s+[\w.\-_=+/]{8,}"),
        "Bearer [REDACTED:bearer-token]",
    ),
    # PEM private keys and certificates
    (
        "private-key",
        re.compile(
            r"-----BEGIN [A-Z ]+(?:KEY|CERTIFICATE)-----.*?-----END [A-Z ]+(?:KEY|CERTIFICATE)-----",
            re.DOTALL,
        ),
        "[REDACTED:private-key]",
    ),
    # DB/cache connection strings with embedded credentials
    (
        "connection-string",
        re.compile(
            r"(?:postgresql|mysql|mongodb|redis)://[^\s:@]+:[^\s@]+@\S+"
        ),
        "[REDACTED:connection-string]",
    ),
    # ArgoCD tokens
    (
        "argocd-token",
        re.compile(r"\bargocd_[\w]{16,}\b"),
        "[REDACTED:argocd-token]",
    ),
]


class RedactionResult(NamedTuple):
    text: str
    labels: list[str]


def redact(text: str) -> RedactionResult:
    """Redact secrets from *text* before sending to an LLM provider.

    Returns RedactionResult(redacted_text, labels) where labels is a
    deduplicated list of rule names that fired, in first-occurrence order.
    """
    result = text
    seen: dict[str, None] = {}  # ordered set via insertion-ordered dict

    for label, pattern, replacement in _RULES:
        new_result, n = pattern.subn(replacement, result)
        if n > 0:
            seen[label] = None
            result = new_result

    return RedactionResult(text=result, labels=list(seen))
