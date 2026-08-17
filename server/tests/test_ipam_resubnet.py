from unittest.mock import patch

import ipam_scan


def _create_subnet(client, cidr):
    resp = client.post("/api/ipam/subnets", json={"cidr": cidr})
    assert resp.status_code == 200
    return resp.json()["id"]


def _add_address(client, subnet_id, address, **fields):
    payload = {"address": address, "status": "used"}
    payload.update(fields)
    resp = client.post(f"/api/ipam/subnets/{subnet_id}/addresses", json=payload)
    assert resp.status_code == 200
    addresses_by_ip = {a["address"]: a for a in resp.json()["addresses"]}
    return addresses_by_ip[address]["id"]


# --- Step 12.7: detection logic ---------------------------------------


def test_misplaced_address_detected_in_broader_subnet(client):
    broad_id = _create_subnet(client, "10.1.0.0/16")
    narrow_id = _create_subnet(client, "10.1.8.0/21")
    _add_address(client, broad_id, "10.1.11.30")

    resp = client.get("/api/ipam/misplaced-addresses")
    assert resp.status_code == 200
    entries = resp.json()

    assert len(entries) == 1
    entry = entries[0]
    assert entry["currentSubnetCidr"] == "10.1.0.0/16"
    assert entry["proposedSubnetCidr"] == "10.1.8.0/21"
    assert entry["currentSubnetId"] == broad_id
    assert entry["proposedSubnetId"] == narrow_id


def test_address_already_in_most_specific_subnet_not_flagged(client):
    _create_subnet(client, "10.1.0.0/16")
    narrow_id = _create_subnet(client, "10.1.8.0/21")
    _add_address(client, narrow_id, "10.1.11.30")

    resp = client.get("/api/ipam/misplaced-addresses")
    assert resp.status_code == 200
    entries = resp.json()

    assert entries == []


def test_address_with_no_more_specific_subnet_not_flagged(client):
    subnet_id = _create_subnet(client, "10.2.0.0/24")
    _add_address(client, subnet_id, "10.2.0.5")

    resp = client.get("/api/ipam/misplaced-addresses")
    assert resp.status_code == 200
    entries = resp.json()

    assert entries == []


def test_misplaced_address_picks_most_specific_of_several_candidates(client):
    broad_id = _create_subnet(client, "10.3.0.0/16")
    mid_id = _create_subnet(client, "10.3.8.0/21")
    narrow_id = _create_subnet(client, "10.3.8.0/24")
    _add_address(client, broad_id, "10.3.8.5")

    resp = client.get("/api/ipam/misplaced-addresses")
    assert resp.status_code == 200
    entries = resp.json()

    assert len(entries) == 1
    entry = entries[0]
    assert entry["currentSubnetCidr"] == "10.3.0.0/16"
    assert entry["proposedSubnetId"] == narrow_id
    assert entry["proposedSubnetCidr"] == "10.3.8.0/24"
    assert entry["proposedSubnetId"] != mid_id


# --- Step 12.8: move endpoint -------------------------------------------


def test_move_address_relocates_it(client):
    broad_id = _create_subnet(client, "10.1.0.0/16")
    narrow_id = _create_subnet(client, "10.1.8.0/21")
    address_id = _add_address(client, broad_id, "10.1.11.30", hostname="host-a", status="used")

    move_resp = client.post(
        f"/api/ipam/subnets/{broad_id}/addresses/{address_id}/move",
        json={"targetSubnetId": narrow_id},
    )
    assert move_resp.status_code == 200

    broad_detail = client.get(f"/api/ipam/subnets/{broad_id}").json()
    assert all(a["address"] != "10.1.11.30" for a in broad_detail["addresses"])

    narrow_detail = client.get(f"/api/ipam/subnets/{narrow_id}").json()
    moved = next(a for a in narrow_detail["addresses"] if a["address"] == "10.1.11.30")
    assert moved["hostname"] == "host-a"
    assert moved["status"] == "used"


def test_move_address_400_for_unknown_source_address(client):
    # The move endpoint catches every ValueError from db.move_address
    # (not-found and validation alike) and maps it to 400, matching
    # edit_address's convention rather than delete_address's 404 -- see
    # step 12.6. "Address not found in source subnet" is one such
    # ValueError, so this resolves to 400, not 404.
    subnet_id = _create_subnet(client, "10.4.0.0/24")
    other_id = _create_subnet(client, "10.4.0.0/28")

    move_resp = client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses/999999/move",
        json={"targetSubnetId": other_id},
    )
    assert move_resp.status_code == 400


def test_move_address_400_when_address_outside_destination_cidr(client):
    subnet_a_id = _create_subnet(client, "10.5.0.0/24")
    subnet_b_id = _create_subnet(client, "10.6.0.0/24")
    address_id = _add_address(client, subnet_a_id, "10.5.0.5")

    move_resp = client.post(
        f"/api/ipam/subnets/{subnet_a_id}/addresses/{address_id}/move",
        json={"targetSubnetId": subnet_b_id},
    )
    assert move_resp.status_code == 400


def test_move_address_preserves_metadata(client):
    broad_id = _create_subnet(client, "10.1.0.0/16")
    narrow_id = _create_subnet(client, "10.1.8.0/21")
    address_id = _add_address(
        client,
        broad_id,
        "10.1.11.30",
        team="net-ops",
        machineType="vm",
        vmCluster="cluster-a",
        environment="prod",
        locked=True,
    )

    move_resp = client.post(
        f"/api/ipam/subnets/{broad_id}/addresses/{address_id}/move",
        json={"targetSubnetId": narrow_id},
    )
    assert move_resp.status_code == 200

    narrow_detail = client.get(f"/api/ipam/subnets/{narrow_id}").json()
    moved = next(a for a in narrow_detail["addresses"] if a["address"] == "10.1.11.30")
    assert moved["team"] == "net-ops"
    assert moved["machineType"] == "vm"
    assert moved["vmCluster"] == "cluster-a"
    assert moved["environment"] == "prod"
    assert moved["locked"] is True


# --- Regression: rescanning a broader subnet must not recreate a host  ---
# --- that was already moved into a more specific subnet.               ---


def test_rescanning_broad_subnet_does_not_recreate_moved_host(client):
    broad_id = _create_subnet(client, "10.9.0.0/24")
    narrow_id = _create_subnet(client, "10.9.0.16/28")
    address_id = _add_address(client, broad_id, "10.9.0.20", hostname="host-a")

    move_resp = client.post(
        f"/api/ipam/subnets/{broad_id}/addresses/{address_id}/move",
        json={"targetSubnetId": narrow_id},
    )
    assert move_resp.status_code == 200

    def fake_ping_host(address, *args, **kwargs):
        return address == "10.9.0.20"

    with patch.object(ipam_scan, "ping_host", side_effect=fake_ping_host), \
         patch.object(ipam_scan, "reverse_dns", return_value="host-a"):
        scan_resp = client.post(f"/api/ipam/subnets/{broad_id}/autodiscover")
    assert scan_resp.status_code == 200

    broad_detail = client.get(f"/api/ipam/subnets/{broad_id}").json()
    assert all(a["address"] != "10.9.0.20" for a in broad_detail["addresses"])

    narrow_detail = client.get(f"/api/ipam/subnets/{narrow_id}").json()
    assert any(a["address"] == "10.9.0.20" for a in narrow_detail["addresses"])

    # The host must not be re-flagged for another resubnet review either.
    misplaced_resp = client.get("/api/ipam/misplaced-addresses")
    assert misplaced_resp.status_code == 200
    assert all(e["address"] != "10.9.0.20" for e in misplaced_resp.json())