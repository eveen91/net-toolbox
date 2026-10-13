import db


def _subnet(client, cidr):
    response = client.post("/api/ipam/subnets", json={"cidr": cidr})
    assert response.status_code == 200
    return response.json()["id"]


def _address(client, subnet_id, address):
    response = client.post(f"/api/ipam/subnets/{subnet_id}/addresses", json={"address": address, "status": "used"})
    assert response.status_code == 200
    return next(row["id"] for row in db.get_addresses_by_subnet(subnet_id) if row["address"] == address)


def test_address_archives_with_reason_and_restores(client):
    subnet_id = _subnet(client, "10.20.0.0/24")
    address_id = _address(client, subnet_id, "10.20.0.10")
    assert client.request("DELETE", f"/api/ipam/subnets/{subnet_id}/addresses/{address_id}", json={"reason": "Decommissioned"}).status_code == 200
    archive = next(row for row in client.get("/api/ipam/archives").json() if row["resource_type"] == "address")
    assert archive["reason"] == "Decommissioned"
    assert archive["snapshot"]["address"] == "10.20.0.10"
    assert client.post(f"/api/ipam/archives/{archive['id']}/restore").status_code == 200
    assert any(row["id"] == address_id for row in db.get_addresses_by_subnet(subnet_id))


def test_subnet_archive_snapshots_children_and_restores(client):
    subnet_id = _subnet(client, "10.21.0.0/24")
    _address(client, subnet_id, "10.21.0.10")
    assert client.request("DELETE", f"/api/ipam/subnets/{subnet_id}", json={"reason": "Replaced"}).status_code == 200
    archive = next(row for row in client.get("/api/ipam/archives").json() if row["resource_type"] == "subnet")
    assert archive["snapshot"]["addresses"][0]["address"] == "10.21.0.10"
    assert client.post(f"/api/ipam/archives/{archive['id']}/restore").status_code == 200
    assert db.get_subnet(subnet_id)["cidr"] == "10.21.0.0/24"


def test_dhcp_archive_requires_reason(client):
    subnet_id = _subnet(client, "10.22.0.0/24")
    pool = client.post(f"/api/ipam/subnets/{subnet_id}/dhcp-pools", json={"start_ip": "10.22.0.10", "end_ip": "10.22.0.20"}).json()
    assert client.request("DELETE", f"/api/ipam/subnets/{subnet_id}/dhcp-pools/{pool['id']}", json={}).status_code == 422
    assert client.request("DELETE", f"/api/ipam/subnets/{subnet_id}/dhcp-pools/{pool['id']}", json={"reason": "Retired"}).status_code == 200
    assert any(row["resource_type"] == "dhcp_pool" for row in client.get("/api/ipam/archives").json())


def test_restore_address_revalidates_new_dhcp_conflict_and_keeps_archive(client):
    subnet_id = _subnet(client, "10.23.0.0/24")
    address_id = _address(client, subnet_id, "10.23.0.10")
    assert client.request("DELETE", f"/api/ipam/subnets/{subnet_id}/addresses/{address_id}", json={"reason": "Retired"}).status_code == 200
    archive = client.get("/api/ipam/archives").json()[0]
    assert client.post(f"/api/ipam/subnets/{subnet_id}/dhcp-pools", json={"start_ip": "10.23.0.10", "end_ip": "10.23.0.20"}).status_code == 200
    assert client.post(f"/api/ipam/archives/{archive['id']}/restore").status_code == 409
    assert not db.get_addresses_by_subnet(subnet_id)
    assert client.get("/api/ipam/archives").json()[0]["id"] == archive["id"]


def test_restore_duplicate_returns_conflict_without_losing_archive(client):
    subnet_id = _subnet(client, "10.24.0.0/24")
    address_id = _address(client, subnet_id, "10.24.0.10")
    client.request("DELETE", f"/api/ipam/subnets/{subnet_id}/addresses/{address_id}", json={"reason": "Retired"})
    archive = client.get("/api/ipam/archives").json()[0]
    _address(client, subnet_id, "10.24.0.10")
    assert client.post(f"/api/ipam/archives/{archive['id']}/restore").status_code == 409
    assert len(db.get_addresses_by_subnet(subnet_id)) == 1
    assert client.get("/api/ipam/archives").json()


def test_subnet_restore_preserves_tags_reservations_exclusions_and_schedule(client):
    subnet_id = _subnet(client, "10.25.0.0/24")
    address_id = _address(client, subnet_id, "10.25.0.10")
    tag = client.post('/api/ipam/tags', json={'name': 'archive-test', 'color': '#112233'}).json()
    assert client.post(f"/api/ipam/subnets/{subnet_id}/tags/{tag['id']}").status_code == 200
    assert client.post(f"/api/ipam/addresses/{address_id}/tags/{tag['id']}").status_code == 200
    reservation = db.add_range_reservation(subnet_id, '10.25.0.40', '10.25.0.50', label='Keep this')
    db.add_scan_exclude(subnet_id, '10.25.0.2')
    db.upsert_scan_schedule(subnet_id, 60, False)
    client.request('DELETE', f'/api/ipam/subnets/{subnet_id}', json={'reason': 'Temporary archive'})
    archive = client.get('/api/ipam/archives').json()[0]
    assert client.post(f"/api/ipam/archives/{archive['id']}/restore").status_code == 200
    assert db.get_range_reservations(subnet_id)[0]['id'] == reservation['id']
    assert db.list_scan_excludes(subnet_id) == ['10.25.0.2']
    assert db.get_scan_schedule(subnet_id)['enabled'] is False
    assert client.get(f'/api/ipam/subnets/{subnet_id}/tags').json()[0]['id'] == tag['id']
    assert client.get(f'/api/ipam/addresses/{address_id}/tags').json()[0]['id'] == tag['id']


def test_expired_archive_cannot_be_restored(client):
    subnet_id = _subnet(client, '10.26.0.0/24')
    client.request('DELETE', f'/api/ipam/subnets/{subnet_id}', json={'reason': 'Expired'})
    archive = client.get('/api/ipam/archives').json()[0]
    conn = db.get_connection()
    conn.execute("UPDATE ipam_archives SET expires_at = '2000-01-01T00:00:00+00:00' WHERE id = ?", (archive['id'],))
    conn.commit()
    conn.close()
    assert client.post(f"/api/ipam/archives/{archive['id']}/restore").status_code == 404
    assert client.get('/api/ipam/archives').json() == []
    assert db.get_subnet(subnet_id) is None


def test_restore_and_reservation_events_can_be_filtered_in_audit(client):
    subnet_id = _subnet(client, '10.27.0.0/24')
    reservation = db.add_range_reservation(subnet_id, '10.27.0.30', '10.27.0.40')
    response = client.get('/api/ipam/audit', params={'subnet_id': subnet_id, 'change_type': 'range_reservation_create'})
    assert response.status_code == 200
    assert len(response.json()['entries']) == 1
    db.delete_range_reservation(subnet_id, reservation['id'])
    client.request('DELETE', f'/api/ipam/subnets/{subnet_id}', json={'reason': 'Archive audit'})
    archive = client.get('/api/ipam/archives').json()[0]
    client.post(f"/api/ipam/archives/{archive['id']}/restore")
    response = client.get('/api/ipam/audit', params={'subnet_id': subnet_id, 'change_type': 'archive_restore'})
    assert response.status_code == 200
    assert len(response.json()['entries']) == 1
