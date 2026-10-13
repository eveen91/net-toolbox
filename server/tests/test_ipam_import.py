def test_import_dry_run_reports_errors_without_writing(client):
    records = [
        {"resourceType": "subnet", "cidr": "10.70.0.0/24", "description": "imported"},
        {"resourceType": "address", "subnetCidr": "10.70.0.0/24", "address": "10.70.0.10", "hostname": "host-a"},
        {"resourceType": "address", "subnetCidr": "10.70.0.0/24", "address": "10.71.0.10"},
    ]
    response = client.post("/api/ipam/import", json={"records": records})
    assert response.status_code == 200
    report = response.json()
    assert report["summary"] == {"create": 2, "update": 0, "skip": 0, "error": 1}
    assert client.get("/api/ipam/subnets").json() == []


def test_import_dry_run_reports_duplicate_and_dhcp_conflicts(client):
    subnet = client.post("/api/ipam/subnets", json={"cidr": "10.72.0.0/24"}).json()
    client.post(f"/api/ipam/subnets/{subnet['id']}/addresses", json={"address": "10.72.0.10"})
    records = [
        {"resourceType": "address", "subnetCidr": "10.72.0.0/24", "address": "10.72.0.10"},
        {"resourceType": "dhcp_pool", "subnetCidr": "10.72.0.0/24", "startIp": "10.72.0.5", "endIp": "10.72.0.15"},
    ]
    report = client.post("/api/ipam/import", json={"records": records}).json()
    assert report["summary"] == {"create": 0, "update": 0, "skip": 1, "error": 1}
    assert "conflicts" in report["error"][0]["message"]


def test_import_confirmation_creates_subnet_address_and_dhcp(client):
    records = [
        {"resourceType": "subnet", "cidr": "10.71.0.0/24", "vlan": 120},
        {"resourceType": "address", "subnetCidr": "10.71.0.0/24", "address": "10.71.0.10", "hostname": "host-a"},
        {"resourceType": "dhcp_pool", "subnetCidr": "10.71.0.0/24", "startIp": "10.71.0.100", "endIp": "10.71.0.110"},
    ]
    response = client.post("/api/ipam/import", json={"records": records, "confirm": True})
    assert response.status_code == 200
    subnet = next(item for item in client.get("/api/ipam/subnets").json() if item["cidr"] == "10.71.0.0/24")
    addresses = client.get(f"/api/ipam/subnets/{subnet['id']}/addresses").json()["addresses"]
    pools = client.get(f"/api/ipam/subnets/{subnet['id']}/dhcp-pools").json()
    assert addresses[0]["hostname"] == "host-a"
    assert pools[0]["start_ip"] == "10.71.0.100"
