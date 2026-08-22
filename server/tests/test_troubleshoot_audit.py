import os
import tempfile

import pytest

import troubleshoot_audit


@pytest.fixture
def audit_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(troubleshoot_audit, "DB_PATH", path)
    troubleshoot_audit.init_db()
    yield path
    os.remove(path)


def test_log_success_and_read_back(audit_db):
    troubleshoot_audit.log_command("sw01", "show version", "admin", True, None)
    rows = troubleshoot_audit.get_recent_audit_log()
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] is not None
    assert row["deviceName"] == "sw01"
    assert row["command"] == "show version"
    assert row["username"] == "admin"
    assert row["success"] is True
    assert row["error"] is None
    assert row["createdAt"]


def test_log_failure_records_error_and_null_device(audit_db):
    troubleshoot_audit.log_command(None, "show mac address-table", "admin", False, "auth failed")
    row = troubleshoot_audit.get_recent_audit_log()[0]
    assert row["deviceName"] is None
    assert row["success"] is False
    assert row["error"] == "auth failed"


def test_get_recent_orders_newest_first(audit_db):
    troubleshoot_audit.log_command("sw01", "cmd1", "u", True, None)
    troubleshoot_audit.log_command("sw01", "cmd2", "u", False, "err")
    troubleshoot_audit.log_command("sw01", "cmd3", "u", True, None)
    rows = troubleshoot_audit.get_recent_audit_log()
    assert [r["command"] for r in rows] == ["cmd3", "cmd2", "cmd1"]


def test_get_recent_respects_limit(audit_db):
    for i in range(5):
        troubleshoot_audit.log_command("sw01", f"cmd{i}", "u", True, None)
    assert len(troubleshoot_audit.get_recent_audit_log(limit=3)) == 3
    assert len(troubleshoot_audit.get_recent_audit_log(limit=50)) == 5


def test_log_command_never_raises_when_db_unavailable(audit_db, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(troubleshoot_audit, "get_connection", boom)
    # Logging must never break the feature it's logging for.
    troubleshoot_audit.log_command("sw01", "show version", "admin", True, None)
