from datetime import datetime, timedelta, timezone

import db


def _subnet(client, cidr, description=None):
    response = client.post("/api/ipam/subnets", json={"cidr": cidr, "description": description})
    assert response.status_code == 200
    return response.json()["id"]


def _address(client, subnet_id, address, **fields):
    response = client.post(f"/api/ipam/subnets/{subnet_id}/addresses", json={"address": address, "status": "used", **fields})
    assert response.status_code == 200
    return next(item["id"] for item in db.get_addresses_by_subnet(subnet_id) if item["address"] == address)


def test_data_quality_lists_all_address_rules(client):
    broad_id = _subnet(client, "10.10.0.0/24", "broad")
    narrow_id = _subnet(client, "10.10.0.0/28", "narrow")
    first_id = _address(client, broad_id, "10.10.0.5", hostname="duplicate")
    _address(client, broad_id, "10.10.0.6", hostname="duplicate", team="ops")
    pool_response = client.post(f"/api/ipam/subnets/{broad_id}/dhcp-pools", json={"start_ip": "10.10.0.5", "end_ip": "10.10.0.10"})
    assert pool_response.status_code == 400
    conn = db.get_connection()
    try:
        conn.execute("INSERT INTO ipam_dhcp_pools (subnet_id, start_ip, end_ip, updated_at) VALUES (?, ?, ?, ?)", (broad_id, "10.10.0.5", "10.10.0.10", datetime.now(timezone.utc).isoformat()))
        conn.commit()
    finally:
        conn.close()

    response = client.get("/api/ipam/data-quality/violations")
    assert response.status_code == 200
    violations = response.json()
    rules = {item["rule"] for item in violations}
    assert {"never_scanned", "critical_subnet_metadata", "missing_owner_team", "duplicate_hostname", "static_in_dhcp", "misplaced_subnet"} <= rules
    misplaced = next(item for item in violations if item["rule"] == "misplaced_subnet" and item["addressId"] == first_id)
    assert misplaced["proposedSubnetId"] == narrow_id


def test_data_quality_utilization_and_stale_scan(client):
    subnet_id = _subnet(client, "10.11.0.0/29", "tracked")
    for address in ("10.11.0.1", "10.11.0.2", "10.11.0.3", "10.11.0.4", "10.11.0.5", "10.11.0.6"):
        _address(client, subnet_id, address, team="ops")
    old = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    db.record_scan(subnet_id, old, old, 0, 0, 0, 0, {"newlyUsed": [], "wentQuiet": [], "hostnameChanged": []})

    violations = client.get("/api/ipam/data-quality/violations").json()
    rules = {item["rule"] for item in violations if item["subnetId"] == subnet_id}
    assert "utilization_90" in rules
    assert "stale_scan" in rules


def test_data_quality_mute_requires_reason_and_hides_violation(client):
    subnet_id = _subnet(client, "10.12.0.0/24", "tracked")
    violation = next(item for item in client.get("/api/ipam/data-quality/violations").json() if item["subnetId"] == subnet_id and item["rule"] == "never_scanned")
    assert client.post(f"/api/ipam/data-quality/violations/{violation['id']}/mute", json={"reason": "Scheduled next week"}).status_code == 200
    remaining = client.get("/api/ipam/data-quality/violations").json()
    assert violation["id"] not in {item["id"] for item in remaining}
    assert client.post(f"/api/ipam/data-quality/violations/{violation['id']}/mute", json={"reason": " "}).status_code == 422
