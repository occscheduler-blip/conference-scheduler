"""conftest.py — fixtures for Docker-backed integration tests."""
import os
import socket
import subprocess
from pathlib import Path

import pytest

# --- Force-set local Supabase credentials before any app module is imported ---
# We MUST override (not just setdefault) because production env vars may already
# be set in the shell, and client.py reads SUPABASE_URL/SUPABASE_KEY at import time.

_PROJECT_ROOT = Path(__file__).parent.parent.parent  # tests/ → backend/ → project/
_CLI = os.path.expanduser("~/.local/bin/supabase")

_LOCAL_URL = "http://127.0.0.1:54321"
# Hardcoded SERVICE_ROLE_KEY JWT for this project's local Supabase Docker instance.
# Refresh by running: ~/.local/bin/supabase status
_LOCAL_SERVICE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0"
    ".EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU"
)


def _get_local_service_key() -> str:
    """Try to read SERVICE_ROLE_KEY from 'supabase status -o env'; fall back to hardcoded."""
    try:
        result = subprocess.run(
            [_CLI, "status", "-o", "env"],
            capture_output=True, text=True, timeout=10,
            cwd=_PROJECT_ROOT,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.strip().startswith("SERVICE_ROLE_KEY="):
                    _, _, value = line.partition("=")
                    return value.strip().strip('"').strip("'")
    except Exception:
        pass
    return _LOCAL_SERVICE_KEY


_service_key = _get_local_service_key()

# Force-set — override any production values already in the environment.
os.environ["SUPABASE_URL"] = _LOCAL_URL
os.environ["SUPABASE_KEY"] = _service_key
os.environ.setdefault("BACKEND_API_KEY", "test-api-key")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-testing-only")


def _is_supabase_running() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 54321), timeout=1):
            return True
    except OSError:
        return False


if not _is_supabase_running():
    pytest.fail(
        "Local Supabase is not running. Start it with: ~/.local/bin/supabase start",
        pytrace=False,
    )


@pytest.fixture(scope="session")
def db():
    from tests.db_helper import DbHelper
    helper = DbHelper()
    yield helper
    helper.close()


@pytest.fixture(autouse=True)
def clean_db(db):
    """Truncate all tables before every test — guaranteed clean slate."""
    db.truncate_all()


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


@pytest.fixture()
def h():
    """Valid admin JWT Bearer header shorthand."""
    from app.auth.jwt_utils import encode_jwt
    token = encode_jwt("00000000-0000-0000-0000-000000000001", "admin@hamilton.edu", "admin")
    return {"Authorization": f"Bearer {token}"}
