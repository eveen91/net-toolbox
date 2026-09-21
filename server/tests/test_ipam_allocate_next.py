import threading

import auth
import auth_db


def allocate(client, subnet_id, payload=None):
    return client.post(f"/api/ipam/subnets/{subnet_id}/allocate-next", json=payload or {})


def create_subnet(client, cidr):
    response = client.post("/api/ipam/subnets", json={"cidr": cidr})
    assert response.status_code == 200
    return response.json()["id"]


def test_allocate_next_creates_reserved_address_with_metadata_and_audit(client):
    auth_db.create_role("allocator", ["ipam.read", "ipam.write"])
    user_id = auth_db.create_user("allocator", auth.hash_password("Password123"), role="allocator")
    auth_db.set_setting("require_login", "true")
    assert client.post("/api/auth/login", json={"username": "allocator", "password": "Password123"}).status_code == 200
    subnet_id = create_subnet(client, "10.10.0.0/24")
    response = allocate(client, subnet_id, {
        "hostname": "api-01",
        "description": "API node",
        "team": "platform",
        "machineType": "vm",
        "vmCluster": "cluster-a",
        "environment": "prod",
        "locked": True,
    })

    assert response.status_code == 200
    data = response.json()
    assert data["address"] == {
        "id": data["address"]["id"], "address": "10.10.0.1", "status": "reserved",
        "hostname": "api-01", "description": "API node", "team": "platform",
        "machineType": "vm", "vmCluster": "cluster-a", "environment": "prod",
        "locked": True, "updatedAt": data["address"]["updatedAt"],
    }
    assert data["subnet"]["reservedCount"] == 1
    audit = client.get("/api/ipam/audit", params={"subnet_id": subnet_id}).json()["entries"]
    assert audit[0]["changeType"] == "create"
    assert audit[0]["userId"] == user_id["id"]
    assert audit[0]["newValue"]["address"] == "10.10.0.1"
    auth_db.set_setting("require_login", "false")


def test_allocate_next_skips_existing_records_excludes_and_dhcp_pools(client):
    subnet_id = create_subnet(client, "10.11.0.0/29")
    assert client.post(f"/api/ipam/subnets/{subnet_id}/addresses", json={"address": "10.11.0.1", "status": "used"}).status_code == 200
    assert client.post(f"/api/ipam/subnets/{subnet_id}/scan-excludes", json={"address": "10.11.0.2"}).status_code == 200
    assert client.post(f"/api/ipam/subnets/{subnet_id}/dhcp-pools", json={"start_ip": "10.11.0.3", "end_ip": "10.11.0.4", "name": "DHCP"}).status_code == 200

    response = allocate(client, subnet_id, {"status": "used"})
    assert response.status_code == 200
    assert response.json()["address"]["address"] == "10.11.0.5"
    assert response.json()["address"]["status"] == "used"


def test_allocate_next_returns_error_for_full_or_unknown_subnet(client):
    subnet_id = create_subnet(client, "10.12.0.0/30")
    assert allocate(client, subnet_id).status_code == 200
    assert allocate(client, subnet_id).status_code == 200
    full_response = allocate(client, subnet_id)
    assert full_response.status_code == 400
    assert full_response.json()["detail"] == "No available addresses in this subnet"
    assert allocate(client, 99999).status_code == 404


def test_allocate_next_requires_write_permission(client):
    auth_db.create_role("reader", ["ipam.read"])
    auth_db.create_user("reader", auth.hash_password("Password123"), role="reader")
    auth_db.set_setting("require_login", "true")
    assert client.post("/api/auth/login", json={"username": "reader", "password": "Password123"}).status_code == 200
    assert allocate(client, 1).status_code == 403
    auth_db.set_setting("require_login", "false")


def test_concurrent_allocations_receive_distinct_addresses(client):
    subnet_id = create_subnet(client, "10.13.0.0/29")
    barrier = threading.Barrier(2)
    results = []

    def request():
        with client.__class__(client.app, headers={"X-CSRF-TOKEN": "fixed-csrf-token"}) as concurrent_client:
            barrier.wait()
            results.append(allocate(concurrent_client, subnet_id).json())

    threads = [threading.Thread(target=request) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert {result["address"]["address"] for result in results} == {"10.13.0.1", "10.13.0.2"}
