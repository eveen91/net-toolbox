import csv
import io
import sqlite3

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
    address = db.get_addresses_by_subnet(subnet["id"])[0]
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


def test_address_only_change_is_saved_and_audited(client):
    subnet = client.post("/api/ipam/subnets", json={"cidr": "10.61.70.0/29"}).json()
    created = client.post(
        f"/api/ipam/subnets/{subnet['id']}/addresses",
        json={"address": "10.61.70.1", "status": "used"},
    ).json()
    address_id = db.get_addresses_by_subnet(subnet["id"])[0]["id"]

    response = client.put(
        f"/api/ipam/subnets/{subnet['id']}/addresses/{address_id}",
        json={"address": "10.61.70.2", "status": "used"},
    )
    assert response.status_code == 200
    assert db.get_addresses_by_subnet(subnet["id"])[0]["address"] == "10.61.70.2"

    audit = client.get(f"/api/ipam/audit/address/{address_id}").json()
    update = next(entry for entry in audit if entry["changeType"] == "update")
    assert update["oldValue"]["address"] == "10.61.70.1"
    assert update["newValue"]["address"] == "10.61.70.2"


def test_unified_subnet_audit_query_preserves_address_history_after_cidr_resize(client):
    subnet = client.post("/api/ipam/subnets", json={"cidr": "10.70.0.0/29"}).json()
    client.post(
        f"/api/ipam/subnets/{subnet['id']}/addresses",
        json={"address": "10.70.0.1", "status": "used"},
    )

    response = client.put(
        f"/api/ipam/subnets/{subnet['id']}",
        json={"cidr": "10.70.0.0/28"},
    )
    assert response.status_code == 200

    page = client.get("/api/ipam/audit", params={"subnet_id": subnet["id"]})
    assert page.status_code == 200
    entries = page.json()["entries"]
    address_create = next(entry for entry in entries if entry["changeType"] == "create")
    assert address_create["ipAddress"] == "10.70.0.1"
    assert address_create["subnetCidr"] == "10.70.0.0/29"
    assert {entry["changeType"] for entry in entries} == {
        "create",
        "subnet_create",
        "subnet_update",
    }


def test_unified_audit_query_paginates_and_filters(client):
    subnet = client.post("/api/ipam/subnets", json={"cidr": "10.71.0.0/29"}).json()
    client.post(
        f"/api/ipam/subnets/{subnet['id']}/addresses",
        json={"address": "10.71.0.1", "status": "used"},
    )
    address_id = db.get_addresses_by_subnet(subnet["id"])[0]["id"]

    page = client.get(
        "/api/ipam/audit",
        params={"subnet_id": subnet["id"], "limit": 1, "offset": 1},
    )
    assert page.status_code == 200
    assert page.json()["total"] == 2
    assert page.json()["limit"] == 1
    assert page.json()["offset"] == 1
    assert len(page.json()["entries"]) == 1

    filtered = client.get(
        "/api/ipam/audit",
        params=[("address_id", address_id), ("change_type", "create"), ("change_type", "delete")],
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["entries"][0]["changeType"] == "create"

    created_at = filtered.json()["entries"][0]["createdAt"]
    assert client.get("/api/ipam/audit", params={"start_time": created_at}).json()["total"] >= 1
    assert client.get("/api/ipam/audit", params={"end_time": "2000-01-01T00:00:00+00:00"}).json()["total"] == 0


def test_audit_filters_reject_reversed_dates_and_unsupported_change_types(client):
    reversed_dates = client.get(
        "/api/ipam/audit",
        params={"start_date": "2026-09-22", "end_date": "2026-09-21"},
    )
    assert reversed_dates.status_code == 400
    assert reversed_dates.json()["detail"] == "Audit start time must not be after end time"

    unsupported_type = client.get(
        "/api/ipam/audit",
        params={"change_type": "unsupported"},
    )
    assert unsupported_type.status_code == 422
    assert unsupported_type.json()["detail"] == "Unsupported audit change type: unsupported"


def test_csv_audit_export_has_attachment_username_and_escaping(client):
    user, subnet, address = _create_audit_entry("csv-user")
    db.update_address(
        subnet["id"],
        address["id"],
        address["address"],
        "used",
        description='quoted, "value"',
        user_id=user["id"],
    )

    response = client.get("/api/ipam/audit/export.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(response.text)))
    update = next(row for row in rows if row["changeType"] == "update")
    assert update["username"] == "csv-user"
    assert 'quoted, \\"value\\"' in update["newValue"]


def test_missing_operation_families_are_audited(client):
    subnet_a = client.post("/api/ipam/subnets", json={"cidr": "10.72.0.0/24"}).json()
    subnet_b = client.post("/api/ipam/subnets", json={"cidr": "10.72.0.0/25"}).json()
    pool = client.post(
        f"/api/ipam/subnets/{subnet_b['id']}/dhcp-pools",
        json={"start_ip": "10.72.0.10", "end_ip": "10.72.0.20", "name": "pool"},
    ).json()
    client.put(
        f"/api/ipam/subnets/{subnet_b['id']}/dhcp-pools/{pool['id']}",
        json={"start_ip": "10.72.0.11", "end_ip": "10.72.0.20", "name": "pool-2"},
    )
    client.post(
        f"/api/ipam/subnets/{subnet_b['id']}/dhcp-pools/{pool['id']}/move",
        json={"targetSubnetId": subnet_a["id"]},
    )
    bulk_pool = client.post(
        f"/api/ipam/subnets/{subnet_b['id']}/dhcp-pools",
        json={"start_ip": "10.72.0.40", "end_ip": "10.72.0.50", "name": "bulk-pool"},
    ).json()
    client.post(
        "/api/ipam/dhcp-pools/bulk-move",
        json={"poolIds": [bulk_pool["id"]], "targetSubnetId": subnet_a["id"]},
    )
    client.delete(f"/api/ipam/subnets/{subnet_a['id']}/dhcp-pools/{pool['id']}")
    client.put("/api/ipam/settings", json={"scanConcurrencyLimit": 7})
    tag = client.post("/api/ipam/tags", json={"name": "audit-tag"}).json()
    client.post(f"/api/ipam/subnets/{subnet_a['id']}/tags/{tag['id']}")
    client.delete(f"/api/ipam/subnets/{subnet_a['id']}/tags/{tag['id']}")
    address = client.post(
        f"/api/ipam/subnets/{subnet_a['id']}/addresses",
        json={"address": "10.72.0.30", "status": "used"},
    ).json()
    address_id = next(item["id"] for item in db.get_addresses_by_subnet(subnet_a["id"]) if item["address"] == "10.72.0.30")
    client.post(f"/api/ipam/addresses/{address_id}/tags/{tag['id']}")
    client.delete(f"/api/ipam/addresses/{address_id}/tags/{tag['id']}")
    client.delete(f"/api/ipam/tags/{tag['id']}")

    entries = client.get("/api/ipam/audit", params={"limit": 1000}).json()["entries"]
    change_types = {entry["changeType"] for entry in entries}
    assert {
        "dhcp_pool_create", "dhcp_pool_update", "dhcp_pool_move", "dhcp_pool_bulk_move", "dhcp_pool_delete",
        "settings_update", "tag_create", "tag_delete", "subnet_tag_add",
        "subnet_tag_remove", "address_tag_add", "address_tag_remove",
    }.issubset(change_types)


def test_audit_migration_preserves_subnet_and_dhcp_pool_ids(client):
    subnet = db.create_subnet("10.70.80.0/29")
    db.add_address(subnet["id"], "10.70.80.1")
    address_id = db.get_addresses_by_subnet(subnet["id"])[0]["id"]

    conn = db.get_connection()
    try:
        conn.execute("DROP TABLE ipam_audit_log")
        conn.execute(
            """
            CREATE TABLE ipam_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address_id INTEGER NOT NULL REFERENCES ipam_addresses(id),
                subnet_id INTEGER,
                dhcp_pool_id INTEGER,
                user_id INTEGER,
                change_type TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                description TEXT,
                ip_address TEXT,
                subnet_cidr TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO ipam_audit_log
                (address_id, subnet_id, dhcp_pool_id, change_type, created_at)
            VALUES (?, ?, ?, 'legacy', '2026-01-01T00:00:00+00:00')
            """,
            (address_id, subnet["id"], 84),
        )
        conn.commit()
    finally:
        conn.close()

    db.init_db()

    conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT subnet_id, dhcp_pool_id FROM ipam_audit_log WHERE change_type = 'legacy'"
        ).fetchone()
        assert row["subnet_id"] == subnet["id"]
        assert row["dhcp_pool_id"] == 84
    finally:
        conn.close()
