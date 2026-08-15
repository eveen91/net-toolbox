def test_bulk_update_sets_only_specified_fields(client):
    subnet_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/29"})
    assert subnet_resp.status_code == 200
    subnet_id = subnet_resp.json()["id"]

    add1 = client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses",
        json={
            "address": "10.0.0.1",
            "status": "used",
            "hostname": "host-one",
            "description": "first host",
        },
    )
    assert add1.status_code == 200
    add2 = client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses",
        json={
            "address": "10.0.0.2",
            "status": "used",
            "hostname": "host-two",
            "description": "second host",
        },
    )
    assert add2.status_code == 200
    addresses_by_ip = {a["address"]: a for a in add2.json()["addresses"]}
    id1 = addresses_by_ip["10.0.0.1"]["id"]
    id2 = addresses_by_ip["10.0.0.2"]["id"]

    bulk_resp = client.patch(
        f"/api/ipam/subnets/{subnet_id}/addresses/bulk",
        json={"addressIds": [id1, id2], "team": "net-ops"},
    )
    assert bulk_resp.status_code == 200

    detail = client.get(f"/api/ipam/subnets/{subnet_id}").json()
    by_id = {a["id"]: a for a in detail["addresses"]}

    assert by_id[id1]["team"] == "net-ops"
    assert by_id[id2]["team"] == "net-ops"
    # Fields not sent in the bulk request must survive untouched.
    assert by_id[id1]["hostname"] == "host-one"
    assert by_id[id1]["description"] == "first host"
    assert by_id[id2]["hostname"] == "host-two"
    assert by_id[id2]["description"] == "second host"


def test_bulk_update_forces_vm_cluster_null_when_machine_type_not_vm(client):
    subnet_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.1.0/29"})
    subnet_id = subnet_resp.json()["id"]

    add_resp = client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses",
        json={
            "address": "10.0.1.1",
            "status": "used",
            "machineType": "vm",
            "vmCluster": "cluster-a",
        },
    )
    assert add_resp.status_code == 200
    address_id = add_resp.json()["addresses"][0]["id"]
    assert add_resp.json()["addresses"][0]["vmCluster"] == "cluster-a"

    bulk_resp = client.patch(
        f"/api/ipam/subnets/{subnet_id}/addresses/bulk",
        json={"addressIds": [address_id], "machineType": "physical"},
    )
    assert bulk_resp.status_code == 200

    detail = client.get(f"/api/ipam/subnets/{subnet_id}").json()
    address = next(a for a in detail["addresses"] if a["id"] == address_id)
    assert address["machineType"] == "physical"
    assert address["vmCluster"] is None


def test_bulk_update_respects_explicit_vm_cluster_override(client):
    subnet_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.2.0/29"})
    subnet_id = subnet_resp.json()["id"]

    add_resp = client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses",
        json={
            "address": "10.0.2.1",
            "status": "used",
            "machineType": "vm",
            "vmCluster": "cluster-a",
        },
    )
    assert add_resp.status_code == 200
    address_id = add_resp.json()["addresses"][0]["id"]

    bulk_resp = client.patch(
        f"/api/ipam/subnets/{subnet_id}/addresses/bulk",
        json={
            "addressIds": [address_id],
            "machineType": "physical",
            "vmCluster": "keep-me",
        },
    )
    assert bulk_resp.status_code == 200

    detail = client.get(f"/api/ipam/subnets/{subnet_id}").json()
    address = next(a for a in detail["addresses"] if a["id"] == address_id)
    assert address["machineType"] == "physical"
    assert address["vmCluster"] == "keep-me"


def test_bulk_update_skips_addresses_from_other_subnets(client):
    subnet_a_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.3.0/29"})
    subnet_a_id = subnet_a_resp.json()["id"]
    subnet_b_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.4.0/29"})
    subnet_b_id = subnet_b_resp.json()["id"]

    add_a = client.post(
        f"/api/ipam/subnets/{subnet_a_id}/addresses",
        json={"address": "10.0.3.1", "status": "used"},
    )
    assert add_a.status_code == 200
    address_a_id = add_a.json()["addresses"][0]["id"]

    add_b = client.post(
        f"/api/ipam/subnets/{subnet_b_id}/addresses",
        json={"address": "10.0.4.1", "status": "used", "team": "original-team"},
    )
    assert add_b.status_code == 200
    address_b_id = add_b.json()["addresses"][0]["id"]

    # Bulk-update subnet A, but sneak in subnet B's address id too.
    bulk_resp = client.patch(
        f"/api/ipam/subnets/{subnet_a_id}/addresses/bulk",
        json={"addressIds": [address_a_id, address_b_id], "team": "should-not-apply"},
    )
    assert bulk_resp.status_code == 200

    subnet_b_detail = client.get(f"/api/ipam/subnets/{subnet_b_id}").json()
    address_b = next(a for a in subnet_b_detail["addresses"] if a["id"] == address_b_id)
    assert address_b["team"] == "original-team"


def test_bulk_update_rejects_empty_address_list(client):
    subnet_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.5.0/29"})
    subnet_id = subnet_resp.json()["id"]

    bulk_resp = client.patch(
        f"/api/ipam/subnets/{subnet_id}/addresses/bulk",
        json={"addressIds": [], "team": "net-ops"},
    )
    assert bulk_resp.status_code == 400


def test_bulk_update_can_set_status(client):
    subnet_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.6.0/29"})
    subnet_id = subnet_resp.json()["id"]

    add1 = client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses",
        json={"address": "10.0.6.1", "status": "free"},
    )
    assert add1.status_code == 200
    add2 = client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses",
        json={"address": "10.0.6.2", "status": "free"},
    )
    assert add2.status_code == 200
    addresses_by_ip = {a["address"]: a for a in add2.json()["addresses"]}
    id1 = addresses_by_ip["10.0.6.1"]["id"]
    id2 = addresses_by_ip["10.0.6.2"]["id"]

    bulk_resp = client.patch(
        f"/api/ipam/subnets/{subnet_id}/addresses/bulk",
        json={"addressIds": [id1, id2], "status": "reserved"},
    )
    assert bulk_resp.status_code == 200

    detail = client.get(f"/api/ipam/subnets/{subnet_id}").json()
    by_id = {a["id"]: a for a in detail["addresses"]}
    assert by_id[id1]["status"] == "reserved"
    assert by_id[id2]["status"] == "reserved"