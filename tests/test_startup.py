"""Startup/import safety tests (Vercel FUNCTION_INVOCATION_FAILED regression).

Importing app.main must never open a network connection: table creation
runs in the FastAPI lifespan handler instead. Subprocess tests use fresh
interpreters so import-time behavior is observed in isolation.
"""

import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import _normalize_url

ROOT = Path(__file__).resolve().parents[1]
EMPTY_DIR = Path(os.getenv("TEMP", r"C:\Users\lukka\AppData\Local\Temp")) / "opencode"


def _fresh_env(**overrides):
    env = {k: v for k, v in os.environ.items()
           if k not in ("DATABASE_URL", "TESTING", "UPLOAD_DIR")}
    env["PYTHONPATH"] = str(ROOT)
    env.update(overrides)
    return env


def _import_main(env, cwd):
    return subprocess.run(
        [sys.executable, "-c", "import app.main; print('IMPORT OK')"],
        cwd=str(cwd), env=env,
        capture_output=True, text=True, timeout=180,
    )


def test_import_succeeds_with_unreachable_database():
    """The reported outage: import must not connect, even to a dead host."""
    env = _fresh_env(DATABASE_URL="postgresql://u:p@127.0.0.1:9/db")
    proc = _import_main(env, ROOT)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "IMPORT OK" in proc.stdout


def test_missing_database_url_names_environment():
    """Without any URL (no env, no .env nearby), the error must say so."""
    env = _fresh_env()
    proc = _import_main(env, EMPTY_DIR)
    assert proc.returncode != 0
    assert "DATABASE_URL is not set" in proc.stdout or "DATABASE_URL is not set" in proc.stderr


def test_normalize_postgres_scheme():
    assert _normalize_url("postgres://u:p@h:5432/db") == "postgresql://u:p@h:5432/db"
    assert _normalize_url("postgresql://u:p@h:5432/db") == "postgresql://u:p@h:5432/db"
    assert _normalize_url("sqlite:///x.db") == "sqlite:///x.db"


def test_lifespan_skips_table_creation_in_testing(client, monkeypatch):
    """TESTING=1 (the suite default): entering the app must not touch DDL."""
    import app.main as main

    called = []
    monkeypatch.setattr(
        main.Base.metadata, "create_all", lambda bind=None: called.append(bind)
    )
    with TestClient(main.app) as entered:
        assert entered.get("/health").status_code == 200
    assert called == []


def test_lifespan_creates_tables_outside_testing(monkeypatch):
    """Production path: startup (not import) ensures tables exist."""
    import app.main as main

    called = []
    monkeypatch.setattr(
        main.Base.metadata, "create_all", lambda bind=None: called.append(bind)
    )
    monkeypatch.delenv("TESTING", raising=False)
    with TestClient(main.app):
        pass
    assert len(called) == 1
