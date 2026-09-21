import auth
import auth_db


def _login_as(client, username, permissions):
    auth_db.create_role(username, permissions)
    auth_db.create_user(username, auth.hash_password("Password123"), role=username)
    auth_db.set_setting("require_login", "true")
    response = client.post("/api/auth/login", json={"username": username, "password": "Password123"})
    assert response.status_code == 200


def test_ipam_permissions_are_scoped_and_legacy_ipam_remains_compatible(client):
    _login_as(client, "ipam-reader", ["ipam.read"])
    assert client.get("/api/ipam/subnets").status_code == 200
    assert client.post("/api/ipam/subnets", json={"cidr": "10.100.0.0/24"}).status_code == 403
    assert client.put("/api/ipam/settings", json={"scanConcurrencyLimit": 8}).status_code == 403

    client.post("/api/auth/logout")
    _login_as(client, "legacy-ipam", ["ipam"])
    assert client.post("/api/ipam/subnets", json={"cidr": "10.101.0.0/24"}).status_code == 200
    assert client.put("/api/ipam/settings", json={"scanConcurrencyLimit": 8}).status_code == 200

    auth_db.set_setting("require_login", "false")


def test_contextual_audit_csv_requires_read_and_global_export_requires_admin(client):
    _login_as(client, "audit-reader", ["ipam.read"])

    assert client.get("/api/ipam/audit/subnet/1/export.csv").status_code == 200
    assert client.get("/api/ipam/audit/address/1/export.csv").status_code == 200
    assert client.get("/api/ipam/audit/export.csv").status_code == 403
    assert client.get("/api/ipam/audit/export.csv", params={"subnet_id": 1}).status_code == 403

    client.post("/api/auth/logout")
    _login_as(client, "audit-admin", ["ipam.admin"])
    assert client.get("/api/ipam/audit/export.csv").status_code == 200

    auth_db.set_setting("require_login", "false")


def test_ipam_scan_permission_does_not_grant_write_or_admin(client):
    _login_as(client, "ipam-scanner", ["ipam.scan"])
    assert client.get("/api/ipam/subnets").status_code == 403
    assert client.post("/api/ipam/subnets", json={"cidr": "10.102.0.0/24"}).status_code == 403
    assert client.put("/api/ipam/settings", json={"scanConcurrencyLimit": 8}).status_code == 403
    auth_db.set_setting("require_login", "false")
