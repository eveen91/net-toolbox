import asyncio
import csv
import io
import threading
from unittest.mock import Mock

import pytest
import main
from connection_test import runtime
from connection_test.schemas import RunRequest


def payload(**changes):
    return {"sources": [{"host": "linux-source", "os": "linux"}], "destinations": ["destination"], "ports": [443],
            "linux_credentials": {"username": "tester", "password": "test-only"}, **changes}


def test_valid_run_invokes_both_probes_and_exports_escaped_csv(client, monkeypatch):
    status = 'UNREACHABLE (message, "quoted"\nnext line)'
    linux = Mock(return_value=[main.ResultRow(source_host="linux-source", destination="destination", port="443", status=status, timestamp="now")])
    windows = Mock(return_value=[main.ResultRow(source_host="windows-source", destination="destination", port="443", status="OPEN", timestamp="now")])
    monkeypatch.setattr(main, "test_linux_source", linux)
    monkeypatch.setattr(main, "test_windows_source", windows)
    response = client.post("/api/connection-test/run", json=payload(
        sources=[{"host": " linux-source ", "os": "linux"}, {"host": "windows-source", "os": "windows"}],
        destinations=[" destination "], windows_credentials={"username": "tester", "password": "test-only"},
        winrm_transport="basic", winrm_scheme="https", winrm_port=5986))
    assert response.status_code == 200, response.text
    assert len(response.json()["rows"]) == 2
    rows = list(csv.reader(io.StringIO(response.json()["csv"])))
    assert rows[1] == ["linux-source", "destination", "443", status, "now"]
    assert rows[2][3] == "OPEN"
    assert linux.call_args.args[0] == "linux-source"
    assert linux.call_args.args[2:4] == (["destination"], [443])
    assert windows.call_args.args[-3:] == (5986, "basic", "https")


@pytest.mark.parametrize("changes", [
    {"sources": []}, {"destinations": []}, {"ports": []},
    {"ports": [0]}, {"ports": [65536]}, {"ports": [True]}, {"ports": [22.5]}, {"ports": ["22abc"]}, {"ports": ["22"]},
    {"sources": [{"host": "source", "os": "linux"}] * 17},
    {"destinations": ["destination"] * 65}, {"ports": [443] * 33},
    {"sources": [{"host": "source", "os": "linux"}] * 16, "destinations": ["destination"] * 64, "ports": [22, 443]},
    {"destinations": ["host;whoami"]}, {"sources": [{"host": "$(whoami)", "os": "linux"}]},
    {"ssh_port": 0}, {"winrm_port": 65536}, {"connect_timeout_seconds": 61},
    {"winrm_scheme": "http", "winrm_transport": "basic"},
])
def test_invalid_request_rejected_before_scheduling(client, monkeypatch, changes):
    probe = Mock(side_effect=AssertionError("Invalid requests must not reach a device"))
    monkeypatch.setattr(main, "test_linux_source", probe)
    monkeypatch.setattr(main, "test_windows_source", probe)
    assert client.post("/api/connection-test/run", json=payload(**changes)).status_code == 422
    probe.assert_not_called()


def test_limit_boundary_and_missing_credentials_return_results(client):
    response = client.post("/api/connection-test/run", json=payload(
        sources=[{"host": "source", "os": "linux"}] * 16,
        destinations=["destination"] * 64, linux_credentials=None))
    assert response.status_code == 200
    assert len(response.json()["rows"]) == 16
    assert all(row["status"] == "Missing Linux credentials" for row in response.json()["rows"])


def test_busy_run_returns_retry_header(client, monkeypatch):
    slots = threading.BoundedSemaphore(2)
    slots.acquire(); slots.acquire()
    monkeypatch.setattr(runtime, "RUN_SLOTS", slots)
    response = client.post("/api/connection-test/run", json=payload())
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"


def test_cancelled_request_keeps_capacity_until_worker_finishes(monkeypatch):
    slots = threading.BoundedSemaphore(1)
    monkeypatch.setattr(runtime, "RUN_SLOTS", slots)
    started, finish = threading.Event(), threading.Event()
    def probe(*args):
        started.set()
        assert finish.wait(5)
        return []
    async def scenario():
        req = RunRequest(**payload())
        task = asyncio.create_task(runtime.run_sources(req, probe, probe, main._error_row))
        try:
            assert await asyncio.to_thread(started.wait, 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            with pytest.raises(main.HTTPException) as exc:
                await runtime.run_sources(req, probe, probe, main._error_row)
            assert exc.value.status_code == 503
        finally:
            finish.set()
        for _ in range(100):
            if slots.acquire(blocking=False):
                slots.release()
                break
            await asyncio.sleep(.01)
        else:
            pytest.fail("Completed worker did not release capacity")
        assert await runtime.run_sources(req, probe, probe, main._error_row) == []
    asyncio.run(scenario())


def test_connection_permission_and_tenant_context_apply_in_dedicated_workers(client, monkeypatch):
    import auth
    import auth_db
    from tenancy.context import current_tenant
    admin = auth_db.create_user("connection-admin", auth.hash_password("Password123"), role="admin")
    client.post("/api/auth/login", json={"username": "connection-admin", "password": "Password123"})
    tenant = client.post("/api/tenants", json={"name": "Connection tenant"}).json()["id"]
    seen = []
    def probe(*args):
        seen.append(current_tenant.get().tenant_id)
        return []
    monkeypatch.setattr(main, "test_linux_source", probe)
    assert client.post("/api/connection-test/run", headers={"X-Tenant-ID": tenant}, json=payload()).status_code == 200
    assert seen == [tenant]
    auth_db.create_role("connection-denied", ["ipam.read"])
    auth_db.create_user("connection-reader", auth.hash_password("Password123"), role="connection-denied")
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "connection-reader", "password": "Password123"})
    assert client.post("/api/connection-test/run", json=payload()).status_code == 403
    assert seen == [tenant]
