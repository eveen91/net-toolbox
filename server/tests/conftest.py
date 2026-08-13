import os
import tempfile

import pytest
from fastapi.testclient import TestClient

import db
import main


@pytest.fixture
def client(monkeypatch):
    fd, temp_db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # db.py picks its SQLite file via the module-level DB_PATH constant
    # (read fresh by get_connection() on every call), so swapping it here
    # is enough to keep tests off the real server/toolbox.db.
    monkeypatch.setattr(db, "DB_PATH", temp_db_path)

    db.init_db()

    with TestClient(main.app) as test_client:
        yield test_client

    os.remove(temp_db_path)