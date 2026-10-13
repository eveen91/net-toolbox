def test_import_dry_run_then_confirm_workflow(client):
    records = [
        {"resourceType": "subnet", "cidr": "10.80.0.0/24", "vlan": 180, "description": "Imported"},
        {"resourceType": "address", "subnetCidr": "10.80.0.0/24", "address": "10.80.0.10", "hostname": "imported-host"},
        {"resourceType": "dhcp_pool", "subnetCidr": "10.80.0.0/24", "startIp": "10.80.0.100", "endIp": "10.80.0.110"},
    ]
    dry_run = client.post("/api/ipam/import", json={"records": records})
    assert dry_run.status_code == 200
    assert dry_run.json()["ready"] is True
    assert dry_run.json()["summary"] == {"create": 3, "update": 0, "skip": 0, "error": 0}
    assert client.get("/api/ipam/subnets").json() == []

    confirmed = client.post("/api/ipam/import", json={"records": records, "confirm": True})
    assert confirmed.status_code == 200
    subnet = next(row for row in client.get("/api/ipam/subnets").json() if row["cidr"] == "10.80.0.0/24")
    assert subnet["vlan"] == 180
    assert client.get(f"/api/ipam/subnets/{subnet['id']}/addresses").json()["addresses"][0]["hostname"] == "imported-host"


def test_create_subnet_allocate_next_then_add_host_workflow(client):
    created = client.post("/api/ipam/subnets", json={"cidr": "10.81.0.0/29", "description": "Application network"})
    assert created.status_code == 200
    subnet = created.json()

    allocated = client.post(f"/api/ipam/subnets/{subnet['id']}/allocate-next", json={"hostname": "reserved-api", "team": "platform"})
    assert allocated.status_code == 200
    assert allocated.json()["address"]["address"] == "10.81.0.1"
    assert allocated.json()["address"]["status"] == "reserved"

    added = client.post(f"/api/ipam/subnets/{subnet['id']}/addresses", json={"address": "10.81.0.2", "status": "used", "hostname": "app-host", "team": "platform"})
    assert added.status_code == 200
    addresses = client.get(f"/api/ipam/subnets/{subnet['id']}/addresses").json()["addresses"]
    assert {(row["address"], row["hostname"], row["status"]) for row in addresses} == {
        ("10.81.0.1", "reserved-api", "reserved"),
        ("10.81.0.2", "app-host", "used"),
    }
