import auth
import auth_db
import db


def login(client, name, role="admin"):
    user = auth_db.create_user(name, auth.hash_password("Password123"), role=role)
    assert client.post("/api/auth/login", json={"username": name, "password": "Password123"}).status_code == 200
    return user


def test_tenant_databases_isolate_all_persisted_tools(client):
    login(client, "platform")
    tenant = client.post("/api/tenants", json={"name": "Firma B"})
    assert tenant.status_code == 201
    tenant_id = tenant.json()["id"]
    headers = {"X-Tenant-ID": tenant_id}
    assert client.post("/api/ipam/subnets", headers=headers, json={"cidr": "10.1.0.0/24"}).status_code == 200
    assert client.get("/api/ipam/subnets").json() == []
    assert len(client.get("/api/ipam/subnets", headers=headers).json()) == 1
    plan = client.post("/api/validation/plans", headers=headers, json={"name": "B"})
    assert plan.status_code == 201
    assert client.get("/api/validation/plans").json() == []
    assert client.get("/api/validation/plans", headers=headers).json()[0]["name"] == "B"
    assert client.get("/api/devices", headers=headers).json() == []
    assert client.get("/api/routing/hosts", headers=headers).status_code == 200


def test_memberships_roles_revocation_and_no_platform_escalation(client):
    login(client, "platform")
    tenant_id = client.post("/api/tenants", json={"name": "Private"}).json()["id"]
    auth_db.create_role("reader", ["ipam.read"])
    user = auth_db.create_user("member", auth.hash_password("Password123"))
    headers = {"X-Tenant-ID": tenant_id}
    assert client.put(f"/api/tenants/{tenant_id}/members/{user['id']}", json={"role": "reader"}).status_code == 200
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "member", "password": "Password123"})
    assert client.get("/api/ipam/subnets", headers=headers).status_code == 200
    assert client.post("/api/ipam/subnets", headers=headers, json={"cidr": "10.2.0.0/24"}).status_code == 403
    assert client.get("/api/validation/plans", headers=headers).status_code == 403
    assert client.get("/api/tenants/unknown/members").status_code in (403, 404)
    assert client.post("/api/tenants", json={"name": "Forbidden"}).status_code == 403
    assert client.get("/api/ipam/subnets", headers={"X-Tenant-ID": "../auth.db"}).status_code == 403
    auth_db.set_tenant_membership(tenant_id, user["id"], "tenant-admin")
    assert client.get(f"/api/tenants/{tenant_id}/members").status_code == 200
    assert client.get("/api/admin/users", headers=headers).status_code == 403
    auth_db.remove_tenant_membership(tenant_id, user["id"])
    assert client.get("/api/ipam/subnets", headers=headers).status_code == 403


def test_open_mode_is_only_default_and_existing_data_preserved(client):
    subnet = db.create_subnet("10.3.0.0/24")
    auth_db.init_auth_db()
    assert client.get("/api/ipam/subnets").json()[0]["id"] == subnet["id"]
    assert client.get("/api/ipam/subnets", headers={"X-Tenant-ID": "unknown"}).status_code == 403
    login(client, "platform")
    tenant_id = client.post("/api/tenants", json={"name": "Protected"}).json()["id"]
    client.post("/api/auth/logout")
    assert client.get("/api/ipam/subnets", headers={"X-Tenant-ID": tenant_id}).status_code == 401


def test_routing_devices_and_audit_are_isolated_in_worker_threads(client, monkeypatch):
    import troubleshoot_logic
    import troubleshoot_devices
    import troubleshoot_audit
    login(client, "platform")
    tenant_id = client.post("/api/tenants", json={"name": "Worker"}).json()["id"]
    headers = {"X-Tenant-ID": tenant_id}
    payload = {"name": "sw-b", "mgmtIp": "10.4.0.1", "vendor": "Cisco", "model": "C9300", "deviceType": "cisco_ios"}
    assert client.post("/api/devices", headers=headers, json=payload).status_code == 200
    assert client.get("/api/devices").json() == []
    assert client.put("/api/routing/hosts/sw-b", headers=headers, json={"routes": [{"network": "10.4.0.0/24", "nextHop": "directly connected"}]}).status_code == 200
    assert client.get("/api/routing/hosts").json() == []
    assert client.get("/api/routing/hosts/sw-b").status_code == 404

    def fake_diagnostic(*args):
        devices = troubleshoot_devices.list_devices()
        troubleshoot_audit.log_command("sw-b", "show version", "platform", True, None)
        return {"devices": devices}

    monkeypatch.setattr(troubleshoot_logic, "run_full_diagnostic", fake_diagnostic)
    response = client.post("/api/troubleshoot/run", headers=headers, json={"ip": "10.4.0.1", "username": "mock", "password": "mock"})
    assert response.status_code == 200
    assert response.json()["devices"][0]["name"] == "sw-b"
    assert client.get("/api/troubleshoot/audit-log").json() == []
    assert len(client.get("/api/troubleshoot/audit-log", headers=headers).json()) == 1


def test_concurrent_requests_and_overlapping_addresses(client):
    from concurrent.futures import ThreadPoolExecutor
    login(client, "platform")
    tenant_id = client.post("/api/tenants", json={"name": "Parallel"}).json()["id"]
    for selected in ["default", tenant_id]:
        assert client.post("/api/ipam/subnets", headers={"X-Tenant-ID": selected}, json={"cidr": "10.5.0.0/24", "description": selected}).status_code == 200

    def read(selected):
        response = client.get("/api/ipam/subnets", headers={"X-Tenant-ID": selected})
        assert response.status_code == 200
        assert response.json()[0]["description"] == selected
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(read, ["default", tenant_id] * 12))


def test_scan_background_and_stream_keep_tenant_context(client, monkeypatch):
    import ipam_scan
    login(client, "platform")
    tenant_id = client.post("/api/tenants", json={"name": "Scan"}).json()["id"]
    headers = {"X-Tenant-ID": tenant_id}
    subnet_id = client.post("/api/ipam/subnets", headers=headers, json={"cidr": "10.6.0.0/30"}).json()["id"]
    monkeypatch.setattr(ipam_scan, "ping_host", lambda *args: False)
    monkeypatch.setattr(ipam_scan, "reverse_dns", lambda *args: None)
    start = client.post(f"/api/ipam/subnets/{subnet_id}/autodiscover/start", headers=headers)
    assert start.status_code == 200
    job_id = start.json()["jobId"]
    url = f"/api/ipam/subnets/{subnet_id}/autodiscover/stream/{job_id}"
    stream = client.get(url, params={"tenant_id": tenant_id})
    assert stream.status_code == 200
    assert '"status": "done"' in stream.text
    assert client.get(url).status_code == 404
    assert client.get("/api/ipam/subnets").json() == []
    assert client.get(f"/api/ipam/subnets/{subnet_id}/scans", headers=headers).json()


def test_default_membership_migration_is_once_and_roles_are_current(client):
    user = auth_db.create_user("legacy", auth.hash_password("Password123"))
    auth_db.remove_tenant_membership("default", user["id"])
    auth_db.init_auth_db()
    assert auth_db.tenant_role("default", user["id"]) is None
    auth_db.create_role("assigned", ["ipam.read"])
    auth_db.set_tenant_membership("default", user["id"], "assigned")
    assigned = auth_db.get_role_by_name("assigned")
    auth_db.update_role_permissions(assigned["id"], [])
    client.post("/api/auth/login", json={"username": "legacy", "password": "Password123"})
    assert client.get("/api/ipam/subnets").status_code == 403
    import pytest
    with pytest.raises(ValueError, match="assigned"):
        auth_db.delete_role(assigned["id"])


def test_session_permissions_follow_selected_tenant(client):
    login(client, "platform")
    tenant_id = client.post("/api/tenants", json={"name": "Session"}).json()["id"]
    auth_db.create_role("reader", ["ipam.read"])
    user = auth_db.create_user("member", auth.hash_password("Password123"))
    auth_db.set_tenant_membership(tenant_id, user["id"], "reader")
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "member", "password": "Password123"})
    info = client.get("/api/auth/session", headers={"X-Tenant-ID": tenant_id}).json()
    assert info["tenantId"] == tenant_id
    assert info["user"]["permissions"] == ["ipam.read"]
    assert info["user"]["tenantRole"] == "reader"
    assert info["user"]["role"] == "user"
    assert len(info["tenants"]) == 2


def test_scheduler_binds_every_tenant_and_provision_failure_rolls_back(client, monkeypatch, tmp_path):
    import asyncio
    import pytest
    from ipam import scan_service
    from tenancy.context import current_tenant
    from tenancy import service

    login(client, "platform")
    tenant_id = client.post("/api/tenants", json={"name": "Scheduled"}).json()["id"]
    seen = []

    async def end_iteration(*args):
        raise asyncio.CancelledError

    # Keep a reference to the real yield before replacing scheduler's sleep.
    real_sleep = asyncio.sleep
    async def due_with_yield():
        context = current_tenant.get()
        seen.append(context.tenant_id)
        await real_sleep(0)
        assert current_tenant.get().tenant_id == context.tenant_id
        db.create_subnet("10.7.0.0/24", description=context.tenant_id)

    monkeypatch.setattr(scan_service, "run_due_scan_schedules", due_with_yield)
    monkeypatch.setattr(scan_service, "cleanup_old_scan_jobs", lambda: None)
    monkeypatch.setattr(scan_service.asyncio, "sleep", end_iteration)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(scan_service.scan_scheduler_loop())
    assert set(seen) == {"default", tenant_id}
    assert client.get("/api/ipam/subnets").json()[0]["description"] == "default"
    assert client.get("/api/ipam/subnets", headers={"X-Tenant-ID": tenant_id}).json()[0]["description"] == tenant_id

    def broken(tenant):
        raise RuntimeError("migration failure")
    monkeypatch.setattr(service, "initialize_tenant", broken)
    root = tmp_path / "tenants"
    before = set(root.iterdir())
    with pytest.raises(RuntimeError, match="migration failure"):
        service.create_tenant("Incomplete", 1)
    assert set(root.iterdir()) == before
    assert "Incomplete" not in [t["name"] for t in auth_db.list_tenants(auth_db.get_user_by_username("platform"))]


def test_upgrade_from_pre_tenant_auth_preserves_accounts_sessions_and_data(client):
    user = auth_db.create_user("before-upgrade", auth.hash_password("Password123"))
    auth_db.create_session(user["id"], "existing-session")
    db.create_subnet("10.8.0.0/24", description="Existing data")
    conn = auth_db.get_connection()
    try:
        # Reproduce the actual pre-tenant schema without touching user/session
        # tables, then run the same idempotent startup migration as production.
        conn.execute("DROP TABLE tenant_memberships")
        conn.execute("DROP TABLE tenant_audit")
        conn.execute("DROP TABLE tenants")
        conn.execute("DELETE FROM app_settings WHERE key = 'tenant_memberships_v1'")
        conn.commit()
    finally:
        conn.close()
    auth_db.init_auth_db()
    assert auth_db.get_user_by_session_token("existing-session")["id"] == user["id"]
    assert auth_db.tenant_role("default", user["id"]) == "user"
    assert client.get("/api/ipam/subnets").json()[0]["description"] == "Existing data"
    auth_db.remove_tenant_membership("default", user["id"])
    auth_db.init_auth_db()
    assert auth_db.tenant_role("default", user["id"]) is None


def test_first_install_can_discover_and_create_platform_administrator(client):
    status = client.get("/api/admin/bootstrap-status")
    assert status.status_code == 200
    assert status.json()["adminExists"] is False
    bootstrap = client.post("/api/admin/bootstrap", json={"username": "first-admin", "password": "Password123"})
    assert bootstrap.status_code == 200
    assert client.post("/api/tenants", json={"name": "First tenant"}).status_code == 201
