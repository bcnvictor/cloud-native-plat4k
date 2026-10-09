import sys

import pytest

pytestmark = pytest.mark.keycloak_infra


def test_process_helper_never_logs_sensitive_stdin(caplog):
    from infra.keycloak.lib.commands import run

    with pytest.raises(RuntimeError) as caught:
        run(
            [
                sys.executable,
                "-c",
                "import sys; sys.stderr.buffer.write(sys.stdin.buffer.read()); sys.exit(2)",
            ],
            stdin=b"operator-secret",
        )
    assert "operator-secret" not in str(caught.value) + caplog.text
