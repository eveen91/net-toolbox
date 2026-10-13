"""Routing map CRUD/export and permissions across tenant databases."""
import auth
import auth_db


def setup_tenants(client):
    auth_db.create_user("platform-routing", auth.hash_password("Password123"), role="admin")
    assert client.post("/api/auth/login", json={"username": "platform-routing", "password": "Password123"}).status_code == 200
    created = client.post("/api/tenants", json={"name": "Routing tenant"})
    assert created.status_code == 201
    return created.json()["id"]


def test_routing_crud_export_isolate_identical_host_names(client):
    tenant_id = setup_tenants(client)
    path = "/api/routing/hosts/same-router"
    for tenant, network in [("default", "10.10.0.0/24"), (tenant_id, "10.20.0.0/24")]:
        result = client.put(path, headers={"X-Tenant-ID": tenant}, json={
            "routes": [{"network": network, "nextHop": "directly connected", "interface": "eth0"}],
            "interfaces": [{"name": "eth0", "ipAddress": network.replace(".0/24", ".1/24"), "description": tenant}],
        })
        assert result.status_code == 200
        assert result.json()["host"] == "same-router"
    headers = {"X-Tenant-ID": tenant_id}
    assert client.get(path).json()["routes"][0]["network"] == "10.10.0.0/24"
    assert client.get(path, headers=headers).json()["routes"][0]["network"] == "10.20.0.0/24"
    assert client.get("/api/routing/export").json()[0]["interfaces"][0]["description"] == "default"
    assert client.get("/api/routing/export", headers=headers).json()[0]["interfaces"][0]["description"] == tenant_id
    assert client.put(path, headers=headers, json={"routes": [{"network": "10.30.0.0/24", "nextHop": "directly connected"}]}).status_code == 200
    assert client.get(path).json()["routes"][0]["network"] == "10.10.0.0/24"
    assert client.delete(path, headers=headers).status_code == 200
    assert client.get(path, headers=headers).status_code == 404
    assert client.get("/api/routing/export", headers=headers).json() == []
    assert len(client.get("/api/routing/hosts").json()) == 1
    assert client.get(path).status_code == 200


def test_routing_permission_and_membership_apply_to_every_endpoint(client):
    tenant_id = setup_tenants(client)
    auth_db.create_role("routing-only", ["routing-map"])
    auth_db.create_role("no-routing", ["ipam.read"])
    member = auth_db.create_user("routing-member", auth.hash_password("Password123"), role="no-routing")
    auth_db.set_tenant_membership(tenant_id, member["id"], "routing-only")
    auth_db.set_setting("require_login", "true")
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "routing-member", "password": "Password123"})
    headers = {"X-Tenant-ID": tenant_id}
    path = "/api/routing/hosts/router"
    payload = {"routes": [{"network": "10.40.0.0/24", "nextHop": "directly connected"}]}
    assert client.put(path, headers=headers, json=payload).status_code == 200
    for endpoint in ["/api/routing/hosts", "/api/routing/export", path]:
        assert client.get(endpoint, headers=headers).status_code == 200
        assert client.get(endpoint).status_code == 403
    assert client.put(path, json=payload).status_code == 403
    assert client.delete(path).status_code == 403
    auth_db.remove_tenant_membership(tenant_id, member["id"])
    for endpoint in ["/api/routing/hosts", "/api/routing/export", path]:
        assert client.get(endpoint, headers=headers).status_code == 403
    assert client.put(path, headers=headers, json=payload).status_code == 403
    assert client.delete(path, headers=headers).status_code == 403


def test_move_host_preserves_routes_interfaces_and_audits_both_tenants(client):
    tenant_id = setup_tenants(client)
    path = "/api/routing/hosts/to-move"
    saved = client.put(path, json={"routes": [{"network": "10.50.0.0/24", "nextHop": "directly connected", "interface": "eth0"}],
        "interfaces": [{"name": "eth0", "ipAddress": "10.50.0.1/24", "description": "uplink"}]}).json()
    assert client.get("/api/routing/move-targets").json()[0]["id"] == tenant_id
    preview = client.get(path + "/move-preview", params={"targetTenantId": tenant_id})
    assert preview.status_code == 200
    assert preview.json()["routeCount"] == 1
    result = client.post(path + "/move", json={"targetTenantId": tenant_id, "expectedVersion": preview.json()["version"]})
    assert result.status_code == 200
    assert client.get(path).status_code == 404
    assert client.get(path, headers={"X-Tenant-ID": tenant_id}).json() == saved
    for tenant in ["default", tenant_id]:
        audit = client.get(f"/api/tenants/{tenant}/audit").json()
        assert audit[0]["action"] == "routing_host_move"
        assert 'to-move' in audit[0]["details"]


def test_move_rejects_conflict_stale_preview_and_same_tenant(client):
    tenant_id = setup_tenants(client)
    path = "/api/routing/hosts/conflict"
    data = {"routes": [{"network": "10.60.0.0/24", "nextHop": "directly connected"}]}
    client.put(path, json=data)
    preview = client.get(path + "/move-preview", params={"targetTenantId": tenant_id}).json()
    client.put(path, json={"routes": [{"network": "10.61.0.0/24", "nextHop": "directly connected"}]})
    assert client.post(path + "/move", json={"targetTenantId": tenant_id, "expectedVersion": preview["version"]}).status_code == 409
    assert client.get(path).status_code == 200
    assert client.get(path, headers={"X-Tenant-ID": tenant_id}).status_code == 404
    client.put(path, headers={"X-Tenant-ID": tenant_id}, json=data)
    assert client.get(path + "/move-preview", params={"targetTenantId": tenant_id}).status_code == 409
    assert client.post(path + "/move", json={"targetTenantId": tenant_id, "expectedVersion": preview["version"]}).status_code == 409
    assert client.get(path + "/move-preview", params={"targetTenantId": "default"}).status_code == 400
    assert client.get(path).json()["routes"][0]["network"] == "10.61.0.0/24"
    assert client.get(path, headers={"X-Tenant-ID": tenant_id}).json()["routes"][0]["network"] == "10.60.0.0/24"


def test_move_requires_routing_permission_in_both_tenants_and_a_session(client):
    tenant_id = setup_tenants(client)
    path = "/api/routing/hosts/protected"
    client.put(path, json={"routes": []})
    auth_db.create_role("routing-mover", ["routing-map"])
    member = auth_db.create_user("mover", auth.hash_password("Password123"), role="routing-mover")
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "mover", "password": "Password123"})
    assert client.get("/api/routing/move-targets").json() == []
    assert client.get(path + "/move-preview", params={"targetTenantId": tenant_id}).status_code == 403
    auth_db.set_tenant_membership(tenant_id, member["id"], "routing-mover")
    preview = client.get(path + "/move-preview", params={"targetTenantId": tenant_id}).json()
    auth_db.remove_tenant_membership(tenant_id, member["id"])
    assert client.post(path + "/move", json={"targetTenantId": tenant_id, "expectedVersion": preview["version"]}).status_code == 403
    client.post("/api/auth/logout")
    assert client.get("/api/routing/move-targets").status_code == 401
    assert client.get(path + "/move-preview", params={"targetTenantId": tenant_id}).status_code == 401
    assert client.post(path + "/move", json={"targetTenantId": tenant_id, "expectedVersion": preview["version"]}).status_code == 401


def test_move_rolls_back_source_destination_when_audit_fails(client):
    tenant_id = setup_tenants(client)
    path = "/api/routing/hosts/rollback-router"
    client.put(path, json={"routes": [{"network": "10.70.0.0/24", "nextHop": "directly connected"}]})
    before = client.get(path).json()
    preview = client.get(path + "/move-preview", params={"targetTenantId": tenant_id}).json()
    conn = auth_db.get_connection()
    conn.execute("CREATE TRIGGER reject_move_audit BEFORE INSERT ON tenant_audit WHEN NEW.action = 'routing_host_move' BEGIN SELECT RAISE(ABORT, 'audit failure'); END")
    conn.commit()
    conn.close()
    response = client.post(path + "/move", json={"targetTenantId": tenant_id, "expectedVersion": preview["version"]})
    assert response.status_code == 409
    assert client.get(path).json() == before
    assert client.get(path, headers={"X-Tenant-ID": tenant_id}).status_code == 404
