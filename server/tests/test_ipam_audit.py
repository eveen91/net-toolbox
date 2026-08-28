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
    assert len(entries) == 1
    assert entries[0]["addressId"] == address["id"]
    assert entries[0]["userId"] == user["id"]
    assert entries[0]["username"] == user["username"]


def test_address_and_subnet_audit_logs_resolve_username(client):
    user, subnet, address = _create_audit_entry("history-user")

    address_response = client.get(f'/api/ipam/audit/address/{address["id"]}')
    subnet_response = client.get(f'/api/ipam/audit/subnet/{subnet["id"]}')

    assert address_response.status_code == 200
    assert address_response.json()[0]["username"] == user["username"]
    assert subnet_response.status_code == 200
    assert subnet_response.json()[0]["username"] == user["username"]


def test_audit_log_by_user_resolves_username(client):
    user, _, _ = _create_audit_entry("filtered-user")

    entries = db.get_audit_log_by_user(user["id"])

    assert len(entries) == 1
    assert entries[0]["userId"] == user["id"]
    assert entries[0]["username"] == user["username"]
