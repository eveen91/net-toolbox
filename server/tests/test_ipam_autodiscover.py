import ipaddress
from unittest.mock import patch

import db
import ipam_scan
import main


def test_scan_marks_alive_address_as_used(client):
    create_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/29"})
    assert create_resp.status_code == 200
    subnet_id = create_resp.json()["id"]

    target_address = "10.0.0.3"

    def fake_ping_host(address, *args, **kwargs):
        return address == target_address

    def fake_reverse_dns(address, *args, **kwargs):
        return "myhost.local" if address == target_address else None

    with patch.object(ipam_scan, "ping_host", side_effect=fake_ping_host), \
         patch.object(ipam_scan, "reverse_dns", side_effect=fake_reverse_dns):
        scan_resp = client.post(f"/api/ipam/subnets/{subnet_id}/autodiscover")
    assert scan_resp.status_code == 200

    detail = client.get(f"/api/ipam/subnets/{subnet_id}").json()
    addr = next(a for a in detail["addresses"] if a["address"] == target_address)
    assert addr["status"] == "used"
    assert addr["hostname"] == "myhost.local"


def test_scan_flips_stale_used_address_to_free(client):
    create_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/29"})
    assert create_resp.status_code == 200
    subnet_id = create_resp.json()["id"]

    stale_address = "10.0.0.4"
    add_resp = client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses",
        json={"address": stale_address, "status": "used", "hostname": "oldhost.local"},
    )
    assert add_resp.status_code == 200

    with patch.object(ipam_scan, "ping_host", return_value=False), \
         patch.object(ipam_scan, "reverse_dns", return_value=None):
        scan_resp = client.post(f"/api/ipam/subnets/{subnet_id}/autodiscover")
    assert scan_resp.status_code == 200

    detail = client.get(f"/api/ipam/subnets/{subnet_id}").json()
    addr = next(a for a in detail["addresses"] if a["address"] == stale_address)
    assert addr["status"] == "free"
    assert addr["hostname"] is None


def test_scan_never_pings_reserved_address(client):
    create_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/29"})
    assert create_resp.status_code == 200
    subnet_id = create_resp.json()["id"]

    reserved_address = "10.0.0.5"
    add_resp = client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses",
        json={"address": reserved_address, "status": "reserved"},
    )
    assert add_resp.status_code == 200

    with patch.object(ipam_scan, "ping_host", return_value=True) as mock_ping, \
         patch.object(ipam_scan, "reverse_dns", return_value=None):
        scan_resp = client.post(f"/api/ipam/subnets/{subnet_id}/autodiscover")
    assert scan_resp.status_code == 200

    pinged_addresses = [call.args[0] for call in mock_ping.call_args_list]
    assert reserved_address not in pinged_addresses


def test_scan_preserves_locked_address_even_if_unresponsive(client):
    create_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/29"})
    assert create_resp.status_code == 200
    subnet_id = create_resp.json()["id"]

    locked_address = "10.0.0.6"
    add_resp = client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses",
        json={"address": locked_address, "status": "used", "hostname": "locked-host.local"},
    )
    assert add_resp.status_code == 200
    address_id = next(
        a["id"] for a in add_resp.json()["addresses"] if a["address"] == locked_address
    )

    # There's no API path to set "locked" yet, so set it directly via db.
    db.update_address(
        subnet_id,
        address_id,
        locked_address,
        status="used",
        hostname="locked-host.local",
        locked=True,
    )

    with patch.object(ipam_scan, "ping_host", return_value=False), \
         patch.object(ipam_scan, "reverse_dns", return_value=None):
        scan_resp = client.post(f"/api/ipam/subnets/{subnet_id}/autodiscover")
    assert scan_resp.status_code == 200

    detail = client.get(f"/api/ipam/subnets/{subnet_id}").json()
    addr = next(a for a in detail["addresses"] if a["address"] == locked_address)
    assert addr["status"] == "used"
    assert addr["hostname"] == "locked-host.local"


def test_scan_never_pings_excluded_address(client):
    create_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/29"})
    assert create_resp.status_code == 200
    subnet_id = create_resp.json()["id"]

    excluded_address = "10.0.0.2"
    db.add_scan_exclude(subnet_id, excluded_address)

    with patch.object(ipam_scan, "ping_host", return_value=True) as mock_ping, \
         patch.object(ipam_scan, "reverse_dns", return_value=None):
        scan_resp = client.post(f"/api/ipam/subnets/{subnet_id}/autodiscover")
    assert scan_resp.status_code == 200

    result_addresses = [r["address"] for r in scan_resp.json()["results"]]
    assert excluded_address not in result_addresses

    pinged_addresses = [call.args[0] for call in mock_ping.call_args_list]
    assert excluded_address not in pinged_addresses


def test_concurrent_scan_returns_409(client):
    create_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/29"})
    assert create_resp.status_code == 200
    subnet_id = create_resp.json()["id"]

    main.SCANS_IN_PROGRESS.add(subnet_id)
    try:
        scan_resp = client.post(f"/api/ipam/subnets/{subnet_id}/autodiscover")
        assert scan_resp.status_code == 409
    finally:
        main.SCANS_IN_PROGRESS.discard(subnet_id)


def test_oversized_subnet_returns_400(client):
    create_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/16"})
    assert create_resp.status_code == 200
    subnet_id = create_resp.json()["id"]

    # Sanity-check the fixture actually exceeds the cap we're testing against.
    assert ipaddress.ip_network("10.0.0.0/16").num_addresses > ipam_scan.MAX_SCAN_ADDRESSES

    scan_resp = client.post(f"/api/ipam/subnets/{subnet_id}/autodiscover")
    assert scan_resp.status_code == 400
    detail = scan_resp.json()["detail"]
    assert str(ipam_scan.MAX_SCAN_ADDRESSES) in detail


def test_scan_preserves_metadata_fields(client):
    create_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/29"})
    assert create_resp.status_code == 200
    subnet_id = create_resp.json()["id"]

    target_address = "10.0.0.3"
    add_resp = client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses",
        json={
            "address": target_address,
            "status": "used",
            "team": "networking",
            "machineType": "vm",
            "vmCluster": "cluster-a",
            "environment": "prod",
        },
    )
    assert add_resp.status_code == 200

    with patch.object(ipam_scan, "ping_host", return_value=False), \
         patch.object(ipam_scan, "reverse_dns", return_value=None):
        scan_resp = client.post(f"/api/ipam/subnets/{subnet_id}/autodiscover")
    assert scan_resp.status_code == 200

    detail = client.get(f"/api/ipam/subnets/{subnet_id}").json()
    addr = next(a for a in detail["addresses"] if a["address"] == target_address)
    assert addr["team"] == "networking"
    assert addr["machineType"] == "vm"
    assert addr["vmCluster"] == "cluster-a"
    assert addr["environment"] == "prod"