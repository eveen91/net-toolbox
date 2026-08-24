import os
import tempfile

import pytest
from fastapi.testclient import TestClient

import db
import auth_db
import troubleshoot_devices
import troubleshoot_audit
import main

# Disable the login rate limiter for all tests so repeated login calls in
# fixtures and test sequences are never rejected.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")


@pytest.fixture
def client(monkeypatch):
    fd, temp_db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    auth_fd, temp_auth_db_path = tempfile.mkstemp(suffix=".db")
    os.close(auth_fd)

    # db.py picks its SQLite file via the module-level DB_PATH constant
    # (read fresh by get_connection() on every call), so swapping it here
    # is enough to keep tests off the real server/toolbox.db.
    monkeypatch.setattr(db, "DB_PATH", temp_db_path)

    # auth_db.py keeps credentials in a separate file (AUTH_DB_PATH), so it
    # needs its own temp-file override to keep tests off the real
    # server/auth.db.
    monkeypatch.setattr(auth_db, "AUTH_DB_PATH", temp_auth_db_path)

    # The troubleshoot modules share the same SQLite file as db.py
    # (toolbox.db), so they read the same temp-file override to keep tests
    # off the real server/toolbox.db.
    monkeypatch.setattr(troubleshoot_devices, "DB_PATH", temp_db_path)
    monkeypatch.setattr(troubleshoot_audit, "DB_PATH", temp_db_path)

    db.init_db()
    auth_db.init_auth_db()

    with TestClient(main.app) as test_client:
        yield test_client

    os.remove(temp_db_path)
    os.remove(temp_auth_db_path)