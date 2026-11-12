"""Alembic revision graph sanity — no DB, only parses the migration files.

backend/entrypoint.sh runs `alembic upgrade head` on every deploy to cnp-control:
with two heads (two branches each adding a migration on the same parent) it
fails and the backend doesn't start. Fix by re-parenting the newest migration,
or with `alembic merge heads` if both are already applied somewhere.
"""
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

_BACKEND_DIR = Path(__file__).resolve().parents[1]


def _script_directory() -> ScriptDirectory:
    config = Config(str(_BACKEND_DIR / "alembic.ini"))
    # script_location in alembic.ini is relative to the repo root; pin it so the
    # test doesn't depend on pytest's working directory.
    config.set_main_option("script_location", str(_BACKEND_DIR / "db" / "migrations"))
    return ScriptDirectory.from_config(config)


def test_single_alembic_head():
    heads = _script_directory().get_heads()

    assert len(heads) == 1, f"Multiple Alembic heads {sorted(heads)}: re-parent the newest migration"
