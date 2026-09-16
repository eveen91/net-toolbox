import db
import pytest
import sqlite3


def test_ipam_schema_records_versions_and_indexes(client):
    conn = db.get_connection()
    try:
        versions = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()}
        indexes = {row["name"] for row in conn.execute("PRAGMA index_list(ipam_addresses)").fetchall()}
        assert versions == set(range(1, db.IPAM_SCHEMA_VERSION + 1))
        assert "idx_ipam_addresses_subnet_address" in indexes
        assert "idx_ipam_addresses_hostname" in indexes
    finally:
        conn.close()


def test_ipam_rejects_ipv6_and_invalid_bulk_payloads(client):
    ipv6_subnet = client.post("/api/ipam/subnets", json={"cidr": "2001:db8::/64"})
    assert ipv6_subnet.status_code == 422

    subnet = client.post("/api/ipam/subnets", json={"cidr": "10.110.0.0/24"}).json()
    ipv6_address = client.post(
        f"/api/ipam/subnets/{subnet['id']}/addresses",
        json={"address": "2001:db8::1"},
    )
    assert ipv6_address.status_code == 422

    empty_bulk = client.patch(f"/api/ipam/subnets/{subnet['id']}/addresses/bulk", json={"addressIds": []})
    assert empty_bulk.status_code == 422

    invalid_id_bulk = client.patch(
        f"/api/ipam/subnets/{subnet['id']}/addresses/bulk", json={"addressIds": [0]}
    )
    assert invalid_id_bulk.status_code == 422


def test_ipam_input_normalization_and_limits(client):
    subnet = client.post(
        "/api/ipam/subnets", json={"cidr": " 10.112.0.0/24 ", "description": "   "}
    )
    assert subnet.status_code == 200
    assert subnet.json()["cidr"] == "10.112.0.0/24"
    assert subnet.json()["description"] is None

    address = client.post(
        f"/api/ipam/subnets/{subnet.json()['id']}/addresses",
        json={"address": " 10.112.0.1 ", "hostname": " invalid hostname ", "team": " "},
    )
    assert address.status_code == 422

    oversized_description = client.post(
        "/api/ipam/subnets", json={"cidr": "10.113.0.0/24", "description": "x" * 501}
    )
    assert oversized_description.status_code == 422

    invalid_audit_limit = client.get("/api/ipam/audit/address/1?limit=101&offset=-1")
    assert invalid_audit_limit.status_code == 422


def test_ipam_special_address_policy_allows_point_to_point_and_host_routes(client):
    standard = client.post("/api/ipam/subnets", json={"cidr": "10.111.0.0/30"}).json()
    network_address = client.post(
        f"/api/ipam/subnets/{standard['id']}/addresses", json={"address": "10.111.0.0"}
    )
    broadcast_address = client.post(
        f"/api/ipam/subnets/{standard['id']}/addresses", json={"address": "10.111.0.3"}
    )
    assert network_address.status_code == 400
    assert broadcast_address.status_code == 400

    point_to_point = client.post("/api/ipam/subnets", json={"cidr": "10.111.1.0/31"}).json()
    assert client.post(
        f"/api/ipam/subnets/{point_to_point['id']}/addresses", json={"address": "10.111.1.0"}
    ).status_code == 200


def test_subnet_address_page_supports_filters_sorting_and_bounds(client):
    subnet = client.post("/api/ipam/subnets", json={"cidr": "10.114.0.0/29"}).json()
    for address, status, hostname in (("10.114.0.3", "used", "zeta"), ("10.114.0.1", "free", "alpha"), ("10.114.0.2", "used", "beta")):
        assert client.post(
            f"/api/ipam/subnets/{subnet['id']}/addresses",
            json={"address": address, "status": status, "hostname": hostname},
        ).status_code == 200

    page = client.get(f"/api/ipam/subnets/{subnet['id']}/addresses?limit=1&offset=1&status=used&sort=hostname&direction=desc")
    assert page.status_code == 200
    assert page.json()["total"] == 2
    assert page.json()["addresses"][0]["hostname"] == "beta"
    assert client.get(f"/api/ipam/subnets/{subnet['id']}/addresses?limit=501").status_code == 422
    assert client.post(
        f"/api/ipam/subnets/{point_to_point['id']}/addresses", json={"address": "10.111.1.1"}
    ).status_code == 200

    host_route = client.post("/api/ipam/subnets", json={"cidr": "10.111.2.7/32"}).json()
    assert client.post(
        f"/api/ipam/subnets/{host_route['id']}/addresses", json={"address": "10.111.2.7"}
    ).status_code == 200


def test_interrupted_scan_job_is_released_on_initialization(client):
    subnet = db.create_subnet("10.120.0.0/29")
    assert db.create_scan_job("interrupted-job", subnet["id"])

    db.init_db()

    job = db.get_scan_job("interrupted-job")
    assert job["status"] == "error"
    assert job["error"] == "Scan interrupted by server restart"
    assert db.get_active_scan_job(subnet["id"]) is None


def test_ipam_database_constraints_reject_invalid_domain_values(client):
    subnet = db.create_subnet("10.121.0.0/29")
    conn = db.get_connection()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE ipam_subnets SET vlan = 5000 WHERE id = ?", (subnet["id"],))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO ipam_addresses (subnet_id, address, status, locked, updated_at) VALUES (?, ?, 'invalid', 0, ?)",
                (subnet["id"], "10.121.0.1", "2026-01-01T00:00:00+00:00"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO ipam_dhcp_pools (subnet_id, start_ip, end_ip, updated_at, manually_placed) VALUES (?, ?, ?, ?, 2)",
                (subnet["id"], "10.121.0.2", "10.121.0.3", "2026-01-01T00:00:00+00:00"),
            )
    finally:
        conn.close()


def test_legacy_ipam_schema_is_migrated_to_current_versions(client):
    conn = db.get_connection()
    try:
        conn.execute("DROP TABLE ipam_addresses")
        conn.execute("DROP TABLE ipam_dhcp_pools")
        conn.execute("DELETE FROM schema_migrations")
        conn.execute(
            """
            CREATE TABLE ipam_addresses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subnet_id INTEGER NOT NULL,
                address TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'used',
                hostname TEXT,
                description TEXT,
                updated_at TEXT NOT NULL,
                UNIQUE(subnet_id, address)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE ipam_dhcp_pools (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subnet_id INTEGER NOT NULL,
                start_ip TEXT NOT NULL,
                end_ip TEXT NOT NULL,
                name TEXT,
                description TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    db.init_db()

    conn = db.get_connection()
    try:
        address_columns = {row["name"] for row in conn.execute("PRAGMA table_info(ipam_addresses)").fetchall()}
        pool_columns = {row["name"] for row in conn.execute("PRAGMA table_info(ipam_dhcp_pools)").fetchall()}
        versions = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()}
        assert {"team", "machine_type", "vm_cluster", "environment", "locked"}.issubset(address_columns)
        assert "manually_placed" in pool_columns
        assert versions == set(range(1, db.IPAM_SCHEMA_VERSION + 1))
    finally:
        conn.close()
