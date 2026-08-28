import auth
import auth_db
import db


def _create_audit_entry(username="audit-user"):
    user = auth_db.create_user(username, auth.hash_password("Password123"))
    subnet = db.create_subnet("10.20.30.0/29")
    db.add_address(
        subnet["id"],
        "10.20.30.1",
        hostname="audit-host",
        user_id=user["id"],
    )
    address = db.get_subnet(subnet["id"])["addresses"][0]
    return user, subnet, address


def test_export_audit_log_resolves_username_from_auth_database(client):
    user, _, address = _create_audit_entry()

    response = client.get("/api/ipam/audit/export")

    assert response.status_code == 200
    entries = response.json()
    address_entry = next(entry for entry in entries if entry["changeType"] == "create")
    assert address_entry["addressId"] == address["id"]
    assert address_entry["userId"] == user["id"]
    assert address_entry["username"] == user["username"]


def test_address_and_subnet_audit_logs_resolve_username(client):
    user, subnet, address = _create_audit_entry("history-user")

    address_response = client.get(f'/api/ipam/audit/address/{address["id"]}')
    subnet_response = client.get(f'/api/ipam/audit/subnet/{subnet["id"]}')

    assert address_response.status_code == 200
    assert address_response.json()[0]["username"] == user["username"]
    assert subnet_response.status_code == 200
    address_entry = next(entry for entry in subnet_response.json() if entry["changeType"] == "create")
    assert address_entry["username"] == user["username"]


def test_audit_log_by_user_resolves_username(client):
    user, _, _ = _create_audit_entry("filtered-user")

    entries = db.get_audit_log_by_user(user["id"])

    address_entry = next(entry for entry in entries if entry["changeType"] == "create")
    assert address_entry["userId"] == user["id"]
    assert address_entry["username"] == user["username"]


def test_subnet_create_and_delete_are_audited(client):
    user = auth_db.create_user("subnet-auditor", auth.hash_password("Password123"))
    login = client.post(
        "/api/auth/login",
        json={"username": user["username"], "password": "Password123"},
    )
    assert login.status_code == 200

    create_response = client.post(
        "/api/ipam/subnets",
        json={"cidr": "10.40.50.0/24", "vlan": 4050, "description": "Audit subnet"},
    )
    assert create_response.status_code == 200
    subnet_id = create_response.json()["id"]

    delete_response = client.delete(f"/api/ipam/subnets/{subnet_id}")
    assert delete_response.status_code == 200

    export_response = client.get("/api/ipam/audit/export")
    assert export_response.status_code == 200
    entries = export_response.json()
    create_entry = next(entry for entry in entries if entry["changeType"] == "subnet_create")
    delete_entry = next(entry for entry in entries if entry["changeType"] == "subnet_delete")

    assert create_entry["addressId"] is None
    assert create_entry["subnetId"] == subnet_id
    assert create_entry["username"] == user["username"]
    assert create_entry["newValue"] == {
        "cidr": "10.40.50.0/24",
        "vlan": 4050,
        "description": "Audit subnet",
    }
    assert delete_entry["addressId"] is None
    assert delete_entry["subnetId"] == subnet_id
    assert delete_entry["username"] == user["username"]
    assert delete_entry["oldValue"] == create_entry["newValue"]

    subnet_response = client.get(f"/api/ipam/audit/subnet/{subnet_id}")
    assert subnet_response.status_code == 200
    assert {entry["changeType"] for entry in subnet_response.json()} == {
        "subnet_create",
        "subnet_delete",
    }


def test_deleted_subnet_audit_entries_survive_database_reinitialization(client):
    subnet = db.create_subnet("10.60.70.0/24")
    assert db.delete_subnet(subnet["id"])

    db.init_db()

    entries = db.export_audit_log_csv()
    change_types = {entry["change_type"] for entry in entries}
    assert {"subnet_create", "subnet_delete"}.issubset(change_types)
