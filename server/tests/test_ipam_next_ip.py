def test_empty_subnet_returns_first_host_ip(client):
    """Empty /24 should return 10.0.0.1."""
    resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/24"})
    assert resp.status_code == 200
    subnet_id = resp.json()["id"]

    next_resp = client.get(f"/api/ipam/subnets/{subnet_id}/next-available")
    assert next_resp.status_code == 200
    data = next_resp.json()
    assert data["subnetId"] == subnet_id
    assert data["nextAvailableIp"] == "10.0.0.1"


def test_used_ip_skipped(client):
    """10.0.0.1 used → next should be 10.0.0.2."""
    resp = client.post("/api/ipam/subnets", json={"cidr": "10.1.0.0/24"})
    assert resp.status_code == 200
    subnet_id = resp.json()["id"]

    client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses",
        json={"address": "10.1.0.1", "status": "used"}
    )

    next_resp = client.get(f"/api/ipam/subnets/{subnet_id}/next-available")
    assert next_resp.status_code == 200
    assert next_resp.json()["nextAvailableIp"] == "10.1.0.2"


def test_reserved_ip_also_skipped(client):
    """Reserved IP should be treated as unavailable."""
    resp = client.post("/api/ipam/subnets", json={"cidr": "10.2.0.0/24"})
    assert resp.status_code == 200
    subnet_id = resp.json()["id"]

    client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses",
        json={"address": "10.2.0.1", "status": "reserved"}
    )

    next_resp = client.get(f"/api/ipam/subnets/{subnet_id}/next-available")
    assert next_resp.status_code == 200
    assert next_resp.json()["nextAvailableIp"] == "10.2.0.2"


def test_scan_exclude_skips_ip(client):
    """IP in scan-excludes should be skipped."""
    resp = client.post("/api/ipam/subnets", json={"cidr": "10.3.0.0/24"})
    assert resp.status_code == 200
    subnet_id = resp.json()["id"]

    client.post(
        f"/api/ipam/subnets/{subnet_id}/scan-excludes",
        json={"address": "10.3.0.1"}
    )
    client.post(
        f"/api/ipam/subnets/{subnet_id}/scan-excludes",
        json={"address": "10.3.0.2"}
    )

    next_resp = client.get(f"/api/ipam/subnets/{subnet_id}/next-available")
    assert next_resp.status_code == 200
    assert next_resp.json()["nextAvailableIp"] == "10.3.0.3"


def test_dhcp_pool_range_skips_ips(client):
    """IPs inside a DHCP pool should be unavailable."""
    resp = client.post("/api/ipam/subnets", json={"cidr": "10.4.0.0/24"})
    assert resp.status_code == 200
    subnet_id = resp.json()["id"]

    client.post(
        f"/api/ipam/subnets/{subnet_id}/dhcp-pools",
        json={"start_ip": "10.4.0.10", "end_ip": "10.4.0.20", "name": "DHCP"}
    )

    next_resp = client.get(f"/api/ipam/subnets/{subnet_id}/next-available")
    assert next_resp.status_code == 200
    assert next_resp.json()["nextAvailableIp"] == "10.4.0.1"


def test_full_subnet_returns_null(client):
    """When all host IPs are occupied, nextAvailableIp should be null."""
    resp = client.post("/api/ipam/subnets", json={"cidr": "10.5.0.0/30"})
    assert resp.status_code == 200
    subnet_id = resp.json()["id"]

    # /30 has 2 usable hosts: 10.5.0.1 and 10.5.0.2
    for ip in ["10.5.0.1", "10.5.0.2"]:
        client.post(
            f"/api/ipam/subnets/{subnet_id}/addresses",
            json={"address": ip, "status": "used"}
        )

    next_resp = client.get(f"/api/ipam/subnets/{subnet_id}/next-available")
    assert next_resp.status_code == 200
    assert next_resp.json()["nextAvailableIp"] is None


def test_next_available_ip_404_for_unknown_subnet(client):
    resp = client.get("/api/ipam/subnets/99999/next-available")
    assert resp.status_code == 404


def test_next_available_ip_endpoint_200(client):
    resp = client.post("/api/ipam/subnets", json={"cidr": "10.6.0.0/24"})
    assert resp.status_code == 200
    subnet_id = resp.json()["id"]

    resp = client.get(f"/api/ipam/subnets/{subnet_id}/next-available")
    assert resp.status_code == 200
    data = resp.json()
    assert "subnetId" in data
    assert "nextAvailableIp" in data
