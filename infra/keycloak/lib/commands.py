"""Processes never expose Secret manifests or reflected upstream output in errors."""

import subprocess


def run(
    argv: list[str], stdin: bytes | None = None
) -> subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(
            argv, input=stdin, capture_output=True, timeout=660, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("Operator command could not complete") from None
    if result.returncode:
        raise RuntimeError(f"Operator command failed (exit {result.returncode})")
    return result
