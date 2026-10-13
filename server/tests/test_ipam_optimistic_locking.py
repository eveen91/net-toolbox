import db


def _subnet(client, cidr):
    response = client.post("/api/ipam/subnets", json={"cidr": cidr})
    assert response.status_code == 200
    return response.json()


def _address(client, subnet_id, address):
    response = client.post(f"/api/ipam/subnets/{subnet_id}/addresses", json={"address": address, "status": "used"})
    assert response.status_code == 200
    return next(row for row in db.get_addresses_by_subnet(subnet_id) if row["address"] == address)


def test_subnet_update_rejects_stale_version(client):
    subnet = _subnet(client, "10.30.0.0/24")
    current = client.get(f"/api/ipam/subnets/{subnet['id']}").json()
    assert client.put(f"/api/ipam/subnets/{subnet['id']}", json={"cidr": current["cidr"], "description": "first", "expectedUpdatedAt": current["updatedAt"]}).status_code == 200
    stale = client.put(f"/api/ipam/subnets/{subnet['id']}", json={"cidr": current["cidr"], "description": "stale", "expectedUpdatedAt": current["updatedAt"]})
    assert stale.status_code == 409


def test_address_update_rejects_stale_version(client):
    subnet = _subnet(client, "10.31.0.0/24")
    address = _address(client, subnet["id"], "10.31.0.10")
    payload = {"address": address["address"], "status": address["status"], "expectedUpdatedAt": address["updatedAt"]}
    assert client.put(f"/api/ipam/subnets/{subnet['id']}/addresses/{address['id']}", json={**payload, "hostname": "first"}).status_code == 200
    stale = client.put(f"/api/ipam/subnets/{subnet['id']}/addresses/{address['id']}", json={**payload, "hostname": "stale"})
    assert stale.status_code == 409


def test_dhcp_update_rejects_stale_version(client):
    subnet = _subnet(client, "10.32.0.0/24")
    pool = client.post(f"/api/ipam/subnets/{subnet['id']}/dhcp-pools", json={"start_ip": "10.32.0.10", "end_ip": "10.32.0.20"}).json()
    payload = {"start_ip": pool["start_ip"], "end_ip": pool["end_ip"], "expectedUpdatedAt": pool["updated_at"]}
    assert client.put(f"/api/ipam/subnets/{subnet['id']}/dhcp-pools/{pool['id']}", json={**payload, "name": "first"}).status_code == 200
    stale = client.put(f"/api/ipam/subnets/{subnet['id']}/dhcp-pools/{pool['id']}", json={**payload, "name": "stale"})
    assert stale.status_code == 409


def test_concurrent_writers_cannot_both_use_same_version(client):
    from concurrent.futures import ThreadPoolExecutor
    subnet = _subnet(client, "10.33.0.0/24")
    current = db.get_subnet(subnet['id'])

    def write(description):
        try:
            db.update_subnet(subnet['id'], current['cidr'], description=description, expected_updated_at=current['updatedAt'])
            return 'saved'
        except ValueError as error:
            assert str(error) == 'Record was modified by another user'
            return 'conflict'

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(write, ['first writer', 'second writer'])) == ['conflict', 'saved']
