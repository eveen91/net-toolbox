from unittest.mock import patch

import ipam_scan


def test_create_and_list_scan_exclude(client):
    create_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/29"})
    assert create_resp.status_code == 200
    subnet_id = create_resp.json()["id"]

    excluded_address = "10.0.0.3"
    add_resp = client.post(
        f"/api/ipam/subnets/{subnet_id}/scan-excludes",
        json={"address": excluded_address},
    )
    assert add_resp.status_code == 200
    entries = add_resp.json()
    entry = next(e for e in entries if e["address"] == excluded_address)
    assert isinstance(entry["id"], int)

    list_resp = client.get(f"/api/ipam/subnets/{subnet_id}/scan-excludes")
    assert list_resp.status_code == 200
    addresses = [e["address"] for e in list_resp.json()]
    assert excluded_address in addresses


def test_create_scan_exclude_rejects_address_outside_subnet(client):
    create_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/29"})
    assert create_resp.status_code == 200
    subnet_id = create_resp.json()["id"]

    outside_address = "10.0.1.5"
    add_resp = client.post(
        f"/api/ipam/subnets/{subnet_id}/scan-excludes",
        json={"address": outside_address},
    )
    assert add_resp.status_code == 400


def test_delete_scan_exclude(client):
    create_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/29"})
    assert create_resp.status_code == 200
    subnet_id = create_resp.json()["id"]

    excluded_address = "10.0.0.4"
    add_resp = client.post(
        f"/api/ipam/subnets/{subnet_id}/scan-excludes",
        json={"address": excluded_address},
    )
    assert add_resp.status_code == 200
    exclude_id = next(
        e["id"] for e in add_resp.json() if e["address"] == excluded_address
    )

    delete_resp = client.delete(f"/api/ipam/subnets/{subnet_id}/scan-excludes/{exclude_id}")
    assert delete_resp.status_code == 200

    list_resp = client.get(f"/api/ipam/subnets/{subnet_id}/scan-excludes")
    assert list_resp.status_code == 200
    addresses = [e["address"] for e in list_resp.json()]
    assert excluded_address not in addresses


def test_excluded_address_is_actually_skipped_by_scan(client):
    create_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/29"})
    assert create_resp.status_code == 200
    subnet_id = create_resp.json()["id"]

    excluded_address = "10.0.0.2"
    add_resp = client.post(
        f"/api/ipam/subnets/{subnet_id}/scan-excludes",
        json={"address": excluded_address},
    )
    assert add_resp.status_code == 200

    with patch.object(ipam_scan, "ping_host", return_value=True) as mock_ping, \
         patch.object(ipam_scan, "reverse_dns", return_value=None):
        scan_resp = client.post(f"/api/ipam/subnets/{subnet_id}/autodiscover")
    assert scan_resp.status_code == 200

    result_addresses = [r["address"] for r in scan_resp.json()["results"]]
    assert excluded_address not in result_addresses

    pinged_addresses = [call.args[0] for call in mock_ping.call_args_list]
    assert excluded_address not in pinged_addresses