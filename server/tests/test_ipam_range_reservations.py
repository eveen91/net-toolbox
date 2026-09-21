import asyncio

import db
from ipam import scan_service


def create_subnet(client, cidr="10.90.0.0/29"):
    response = client.post("/api/ipam/subnets", json={"cidr": cidr})
    assert response.status_code == 200
    return response.json()["id"]


def reservation_payload(start="10.90.0.2", end="10.90.0.3", **extra):
    return {"start_ip": start, "end_ip": end, **extra}


def test_legacy_allocation_type_defaults_and_range_indexes(client):
    subnet_id = create_subnet(client)
    client.post(f"/api/ipam/subnets/{subnet_id}/addresses", json={"address": "10.90.0.1", "status": "used"})
    conn = db.get_connection()
    try:
        row = conn.execute("SELECT allocation_type FROM ipam_addresses WHERE subnet_id = ?", (subnet_id,)).fetchone()
        indexes = {row["name"] for row in conn.execute("PRAGMA index_list(ipam_range_reservations)")}
        assert row["allocation_type"] == "static"
        assert "idx_ipam_range_reservations_subnet_status_range" in indexes
    finally:
        conn.close()


def test_range_reservation_crud_validation_overlap_and_audit(client):
    subnet_id = create_subnet(client)
    created = client.post(f"/api/ipam/subnets/{subnet_id}/range-reservations", json=reservation_payload(label="Printers")).json()
    assert created["status"] == "active"
    assert created["allocation_type"] == "reserved_range"
    assert client.post(f"/api/ipam/subnets/{subnet_id}/range-reservations", json=reservation_payload("10.90.0.3", "10.90.0.4")).status_code == 400
    assert client.post(f"/api/ipam/subnets/{subnet_id}/range-reservations", json=reservation_payload("10.90.0.4", "10.90.0.2")).status_code == 400
    assert client.post(f"/api/ipam/subnets/{subnet_id}/range-reservations", json=reservation_payload("10.90.0.0", "10.90.0.1")).status_code == 400
    updated = client.put(f"/api/ipam/subnets/{subnet_id}/range-reservations/{created['id']}", json=reservation_payload(status="released", label="Released")).json()
    assert updated["status"] == "released"
    assert client.get(f"/api/ipam/subnets/{subnet_id}/range-reservations").json()[0]["label"] == "Released"
    assert client.delete(f"/api/ipam/subnets/{subnet_id}/range-reservations/{created['id']}").status_code == 200
    entries = client.get(f"/api/ipam/audit/subnet/{subnet_id}").json()
    assert {"range_reservation_create", "range_reservation_update", "range_reservation_delete"}.issubset({entry["changeType"] for entry in entries})


def test_range_reservation_scope_and_released_reenables_allocation(client):
    subnet_a = create_subnet(client)
    subnet_b = create_subnet(client, "10.91.0.0/29")
    reservation = client.post(f"/api/ipam/subnets/{subnet_a}/range-reservations", json=reservation_payload()).json()
    assert client.put(f"/api/ipam/subnets/{subnet_b}/range-reservations/{reservation['id']}", json=reservation_payload("10.91.0.2", "10.91.0.3")).status_code == 404
    assert client.get(f"/api/ipam/subnets/{subnet_a}/next-available").json()["nextAvailableIp"] == "10.90.0.1"
    client.post(f"/api/ipam/subnets/{subnet_a}/addresses", json={"address": "10.90.0.1", "status": "used"})
    assert client.get(f"/api/ipam/subnets/{subnet_a}/next-available").json()["nextAvailableIp"] == "10.90.0.4"
    response = client.put(f"/api/ipam/subnets/{subnet_a}/range-reservations/{reservation['id']}", json=reservation_payload(status="released"))
    assert response.status_code == 200
    assert client.get(f"/api/ipam/subnets/{subnet_a}/next-available").json()["nextAvailableIp"] == "10.90.0.2"


def test_active_range_reservations_are_excluded_from_scans(client, monkeypatch):
    subnet_id = create_subnet(client)
    response = client.post(f"/api/ipam/subnets/{subnet_id}/range-reservations", json=reservation_payload())
    assert response.status_code == 200
    scanned = []
    monkeypatch.setattr(scan_service.ipam_scan, "scan_one", lambda address, *_: scanned.append(address) or {"address": address, "alive": False, "hostname": None})
    asyncio.run(scan_service.perform_scan(subnet_id))
    assert {"10.90.0.2", "10.90.0.3"}.isdisjoint(scanned)


def test_address_allocation_type_is_independent_of_status(client):
    subnet_id = create_subnet(client)
    response = client.post(f"/api/ipam/subnets/{subnet_id}/addresses", json={"address": "10.90.0.1", "status": "free", "allocationType": "gateway"})
    assert response.status_code == 200
    address = db.get_addresses_by_subnet(subnet_id)[0]
    assert address["status"] == "free"
    assert address["allocationType"] == "gateway"
