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

def test_bulk_delete_removes_selected_addresses(client):
    subnet_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.7.0/29"})
    subnet_id = subnet_resp.json()["id"]

    add1 = client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses",
        json={"address": "10.0.7.1", "status": "used"},
    )
    add2 = client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses",
        json={"address": "10.0.7.2", "status": "used"},
    )
    add3 = client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses",
        json={"address": "10.0.7.3", "status": "used"},
    )
    addresses_by_ip = {a["address"]: a for a in add3.json()["addresses"]}
    id1 = addresses_by_ip["10.0.7.1"]["id"]
    id2 = addresses_by_ip["10.0.7.2"]["id"]
    id3 = addresses_by_ip["10.0.7.3"]["id"]

    del_resp = client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses/bulk-delete",
        json={"addressIds": [id1, id2]},
    )
    assert del_resp.status_code == 200

    detail = client.get(f"/api/ipam/subnets/{subnet_id}").json()
    remaining_ids = {a["id"] for a in detail["addresses"]}
    assert remaining_ids == {id3}


def test_bulk_delete_skips_addresses_from_other_subnets(client):
    subnet_a_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.8.0/29"})
    subnet_a_id = subnet_a_resp.json()["id"]
    subnet_b_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.9.0/29"})
    subnet_b_id = subnet_b_resp.json()["id"]

    add_a = client.post(
        f"/api/ipam/subnets/{subnet_a_id}/addresses",
        json={"address": "10.0.8.1", "status": "used"},
    )
    address_a_id = add_a.json()["addresses"][0]["id"]

    add_b = client.post(
        f"/api/ipam/subnets/{subnet_b_id}/addresses",
        json={"address": "10.0.9.1", "status": "used"},
    )
    address_b_id = add_b.json()["addresses"][0]["id"]

    # Delete on subnet A, but sneak in subnet B's address id too.
    del_resp = client.post(
        f"/api/ipam/subnets/{subnet_a_id}/addresses/bulk-delete",
        json={"addressIds": [address_a_id, address_b_id]},
    )
    assert del_resp.status_code == 200

    subnet_b_detail = client.get(f"/api/ipam/subnets/{subnet_b_id}").json()
    remaining_ids = {a["id"] for a in subnet_b_detail["addresses"]}
    assert remaining_ids == {address_b_id}


def test_bulk_delete_rejects_empty_address_list(client):
    subnet_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.10.0/29"})
    subnet_id = subnet_resp.json()["id"]

    del_resp = client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses/bulk-delete",
        json={"addressIds": []},
    )
    assert del_resp.status_code == 400


def test_bulk_delete_404_for_missing_subnet(client):
    del_resp = client.post(
        "/api/ipam/subnets/999999/addresses/bulk-delete",
        json={"addressIds": [1]},
    )
    assert del_resp.status_code == 404


def test_bulk_move_moves_addresses_to_destination_subnet(client):
    # Move targets follow the same "narrower subnet nested inside a
    # broader one" pattern as the single-address move endpoint (see
    # test_ipam_resubnet.py) — an address can only land in a subnet whose
    # CIDR actually contains it, so the destination here is a /28 nested
    # inside the broader /24 source.
    from_resp = client.post("/api/ipam/subnets", json={"cidr": "10.1.0.0/24"})
    from_id = from_resp.json()["id"]
    to_resp = client.post("/api/ipam/subnets", json={"cidr": "10.1.0.0/28"})
    to_id = to_resp.json()["id"]

    add1 = client.post(
        f"/api/ipam/subnets/{from_id}/addresses",
        json={"address": "10.1.0.1", "status": "used", "hostname": "host-one"},
    )
    add2 = client.post(
        f"/api/ipam/subnets/{from_id}/addresses",
        json={"address": "10.1.0.2", "status": "used", "hostname": "host-two"},
    )
    addresses_by_ip = {a["address"]: a for a in add2.json()["addresses"]}
    id1 = addresses_by_ip["10.1.0.1"]["id"]
    id2 = addresses_by_ip["10.1.0.2"]["id"]

    move_resp = client.post(
        f"/api/ipam/subnets/{from_id}/addresses/bulk-move",
        json={"addressIds": [id1, id2], "targetSubnetId": to_id},
    )
    assert move_resp.status_code == 200
    body = move_resp.json()
    assert body["movedCount"] == 2
    assert body["skipped"] == []
    assert body["fromSubnet"]["addresses"] == []

    to_detail = client.get(f"/api/ipam/subnets/{to_id}").json()
    moved_hostnames = {a["hostname"] for a in to_detail["addresses"]}
    assert moved_hostnames == {"host-one", "host-two"}


def test_bulk_move_skips_address_outside_destination_cidr(client):
    from_resp = client.post("/api/ipam/subnets", json={"cidr": "10.1.2.0/28"})
    from_id = from_resp.json()["id"]
    to_resp = client.post("/api/ipam/subnets", json={"cidr": "10.1.3.0/29"})
    to_id = to_resp.json()["id"]

    add_resp = client.post(
        f"/api/ipam/subnets/{from_id}/addresses",
        json={"address": "10.1.2.1", "status": "used"},
    )
    address_id = add_resp.json()["addresses"][0]["id"]

    move_resp = client.post(
        f"/api/ipam/subnets/{from_id}/addresses/bulk-move",
        json={"addressIds": [address_id], "targetSubnetId": to_id},
    )
    assert move_resp.status_code == 200
    body = move_resp.json()
    assert body["movedCount"] == 0
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["addressId"] == address_id

    from_detail = client.get(f"/api/ipam/subnets/{from_id}").json()
    assert len(from_detail["addresses"]) == 1


def test_bulk_move_skips_duplicate_in_destination(client):
    from_resp = client.post("/api/ipam/subnets", json={"cidr": "10.1.4.0/24"})
    from_id = from_resp.json()["id"]
    to_resp = client.post("/api/ipam/subnets", json={"cidr": "10.1.4.0/28"})
    to_id = to_resp.json()["id"]

    client.post(
        f"/api/ipam/subnets/{to_id}/addresses",
        json={"address": "10.1.4.1", "status": "used"},
    )
    add_resp = client.post(
        f"/api/ipam/subnets/{from_id}/addresses",
        json={"address": "10.1.4.1", "status": "used"},
    )
    address_id = add_resp.json()["addresses"][0]["id"]

    move_resp = client.post(
        f"/api/ipam/subnets/{from_id}/addresses/bulk-move",
        json={"addressIds": [address_id], "targetSubnetId": to_id},
    )
    assert move_resp.status_code == 200
    body = move_resp.json()
    assert body["movedCount"] == 0
    assert len(body["skipped"]) == 1

    from_detail = client.get(f"/api/ipam/subnets/{from_id}").json()
    assert len(from_detail["addresses"]) == 1


def test_bulk_move_partial_success_reports_moved_and_skipped(client):
    from_resp = client.post("/api/ipam/subnets", json={"cidr": "10.1.6.0/24"})
    from_id = from_resp.json()["id"]
    # Narrow destination only covers 10.1.6.0 - 10.1.6.15.
    to_resp = client.post("/api/ipam/subnets", json={"cidr": "10.1.6.0/28"})
    to_id = to_resp.json()["id"]

    add_in_range = client.post(
        f"/api/ipam/subnets/{from_id}/addresses",
        json={"address": "10.1.6.5", "status": "used"},
    )
    id_in_range = add_in_range.json()["addresses"][0]["id"]
    add_out_of_range = client.post(
        f"/api/ipam/subnets/{from_id}/addresses",
        json={"address": "10.1.6.20", "status": "used"},
    )
    addresses_by_ip = {a["address"]: a for a in add_out_of_range.json()["addresses"]}
    id_out_of_range = addresses_by_ip["10.1.6.20"]["id"]

    move_resp = client.post(
        f"/api/ipam/subnets/{from_id}/addresses/bulk-move",
        json={"addressIds": [id_in_range, id_out_of_range], "targetSubnetId": to_id},
    )
    assert move_resp.status_code == 200
    body = move_resp.json()
    assert body["movedCount"] == 1
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["addressId"] == id_out_of_range

    from_detail = client.get(f"/api/ipam/subnets/{from_id}").json()
    assert len(from_detail["addresses"]) == 1
    assert from_detail["addresses"][0]["id"] == id_out_of_range


def test_bulk_move_rejects_empty_address_list(client):
    from_resp = client.post("/api/ipam/subnets", json={"cidr": "10.1.8.0/29"})
    from_id = from_resp.json()["id"]
    to_resp = client.post("/api/ipam/subnets", json={"cidr": "10.1.9.0/29"})
    to_id = to_resp.json()["id"]

    move_resp = client.post(
        f"/api/ipam/subnets/{from_id}/addresses/bulk-move",
        json={"addressIds": [], "targetSubnetId": to_id},
    )
    assert move_resp.status_code == 400


def test_bulk_move_rejects_missing_destination_subnet(client):
    from_resp = client.post("/api/ipam/subnets", json={"cidr": "10.1.10.0/29"})
    from_id = from_resp.json()["id"]
    add_resp = client.post(
        f"/api/ipam/subnets/{from_id}/addresses",
        json={"address": "10.1.10.1", "status": "used"},
    )
    address_id = add_resp.json()["addresses"][0]["id"]

    move_resp = client.post(
        f"/api/ipam/subnets/{from_id}/addresses/bulk-move",
        json={"addressIds": [address_id], "targetSubnetId": 999999},
    )
    assert move_resp.status_code == 400


def test_bulk_move_rejects_same_source_and_destination(client):
    subnet_resp = client.post("/api/ipam/subnets", json={"cidr": "10.1.11.0/29"})
    subnet_id = subnet_resp.json()["id"]
    add_resp = client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses",
        json={"address": "10.1.11.1", "status": "used"},
    )
    address_id = add_resp.json()["addresses"][0]["id"]

    move_resp = client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses/bulk-move",
        json={"addressIds": [address_id], "targetSubnetId": subnet_id},
    )
    assert move_resp.status_code == 400