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

    addresses = db.get_addresses_by_subnet(subnet_id)
    addr = next(a for a in addresses if a["address"] == target_address)
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

    addresses = db.get_addresses_by_subnet(subnet_id)
    addr = next(a for a in addresses if a["address"] == stale_address)
    assert addr["status"] == "free"
    assert addr["hostname"] is None


def test_release_removes_free_address_and_retains_audit_history(client):
    subnet_id = client.post("/api/ipam/subnets", json={"cidr": "10.0.2.0/29"}).json()["id"]
    client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses",
        json={
            "address": "10.0.2.3",
            "status": "free",
            "hostname": "old-host.local",
            "description": "Retired host",
        },
    )
    address = db.get_addresses_by_subnet(subnet_id)[0]

    response = client.post(f"/api/ipam/subnets/{subnet_id}/addresses/{address['id']}/release")

    assert response.status_code == 200
    assert response.json()["freeCount"] == 0
    assert response.json()["recordedCount"] == 0
    assert db.get_addresses_by_subnet(subnet_id) == []
    audit = client.get(f"/api/ipam/audit/address/{address['id']}").json()
    release = next(entry for entry in audit if entry["changeType"] == "release")
    assert release["oldValue"]["status"] == "free"
    assert release["oldValue"]["description"] == "Retired host"
    assert release["newValue"] is None


def test_release_rejects_used_address(client):
    subnet_id = client.post("/api/ipam/subnets", json={"cidr": "10.0.3.0/29"}).json()["id"]
    client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses",
        json={"address": "10.0.3.3", "status": "used"},
    )
    address = db.get_addresses_by_subnet(subnet_id)[0]

    response = client.post(f"/api/ipam/subnets/{subnet_id}/addresses/{address['id']}/release")

    assert response.status_code == 409
    assert response.json()["detail"] == "Only free addresses can be released"
    assert db.get_addresses_by_subnet(subnet_id)[0]["status"] == "used"


def test_released_quiet_address_is_not_recreated_by_scan(client):
    subnet_id = client.post("/api/ipam/subnets", json={"cidr": "10.0.4.0/29"}).json()["id"]
    client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses",
        json={"address": "10.0.4.3", "status": "free"},
    )
    address = db.get_addresses_by_subnet(subnet_id)[0]
    client.post(f"/api/ipam/subnets/{subnet_id}/addresses/{address['id']}/release")

    with patch.object(ipam_scan, "ping_host", return_value=False), patch.object(
        ipam_scan, "reverse_dns", return_value=None
    ):
        response = client.post(f"/api/ipam/subnets/{subnet_id}/autodiscover")

    assert response.status_code == 200
    assert db.get_addresses_by_subnet(subnet_id) == []


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
        a["id"] for a in db.get_addresses_by_subnet(subnet_id) if a["address"] == locked_address
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

    addresses = db.get_addresses_by_subnet(subnet_id)
    addr = next(a for a in addresses if a["address"] == locked_address)
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

    addresses = db.get_addresses_by_subnet(subnet_id)
    addr = next(a for a in addresses if a["address"] == target_address)
    assert addr["team"] == "networking"
    assert addr["machineType"] == "vm"
    assert addr["vmCluster"] == "cluster-a"
    assert addr["environment"] == "prod"


def test_scan_diff_reports_newly_used_address(client):
    create_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/29"})
    assert create_resp.status_code == 200
    subnet_id = create_resp.json()["id"]

    target_address = "10.0.0.3"

    def fake_ping_host(address, *args, **kwargs):
        return address == target_address

    with patch.object(ipam_scan, "ping_host", side_effect=fake_ping_host), \
         patch.object(ipam_scan, "reverse_dns", return_value=None):
        scan_resp = client.post(f"/api/ipam/subnets/{subnet_id}/autodiscover")
    assert scan_resp.status_code == 200

    diff = scan_resp.json()["diff"]
    assert target_address in diff["newlyUsed"]


def test_scan_diff_reports_went_quiet_address(client):
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

    diff = scan_resp.json()["diff"]
    assert stale_address in diff["wentQuiet"]


def test_scan_history_is_recorded(client):
    create_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/29"})
    assert create_resp.status_code == 200
    subnet_id = create_resp.json()["id"]

    target_address = "10.0.0.3"

    def fake_ping_host(address, *args, **kwargs):
        return address == target_address

    with patch.object(ipam_scan, "ping_host", side_effect=fake_ping_host), \
         patch.object(ipam_scan, "reverse_dns", return_value=None):
        scan_resp = client.post(f"/api/ipam/subnets/{subnet_id}/autodiscover")
    assert scan_resp.status_code == 200
    scan_json = scan_resp.json()

    history_resp = client.get(f"/api/ipam/subnets/{subnet_id}/scans")
    assert history_resp.status_code == 200
    history = history_resp.json()
    assert len(history) >= 1

    entry = next(h for h in history if h["id"] == scan_json["scanId"])
    assert entry["scannedCount"] == scan_json["scannedCount"]
    assert entry["usedCount"] == scan_json["usedCount"]
    assert entry["freeCount"] == scan_json["freeCount"]
    assert entry["diff"] == scan_json["diff"]


def test_rescan_single_address_updates_status(client):
    create_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/29"})
    assert create_resp.status_code == 200
    subnet_id = create_resp.json()["id"]

    target_address = "10.0.0.3"
    add_resp = client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses",
        json={"address": target_address, "status": "free"},
    )
    assert add_resp.status_code == 200
    address_id = next(
        a["id"] for a in db.get_addresses_by_subnet(subnet_id) if a["address"] == target_address
    )

    def fake_ping_host(address, *args, **kwargs):
        return address == target_address

    def fake_reverse_dns(address, *args, **kwargs):
        return "single.local" if address == target_address else None

    with patch.object(ipam_scan, "ping_host", side_effect=fake_ping_host), \
         patch.object(ipam_scan, "reverse_dns", side_effect=fake_reverse_dns):
        rescan_resp = client.post(
            f"/api/ipam/subnets/{subnet_id}/addresses/{address_id}/rescan"
        )
    assert rescan_resp.status_code == 200

    addr = next(a for a in db.get_addresses_by_subnet(subnet_id) if a["address"] == target_address)
    assert addr["status"] == "used"
    assert addr["hostname"] == "single.local"


def test_rescan_skips_reserved_address(client):
    create_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/29"})
    assert create_resp.status_code == 200
    subnet_id = create_resp.json()["id"]

    reserved_address = "10.0.0.5"
    add_resp = client.post(
        f"/api/ipam/subnets/{subnet_id}/addresses",
        json={"address": reserved_address, "status": "reserved"},
    )
    assert add_resp.status_code == 200
    address_id = next(
        a["id"] for a in db.get_addresses_by_subnet(subnet_id) if a["address"] == reserved_address
    )

    with patch.object(ipam_scan, "ping_host", return_value=True) as mock_ping, \
         patch.object(ipam_scan, "reverse_dns", return_value=None):
        rescan_resp = client.post(
            f"/api/ipam/subnets/{subnet_id}/addresses/{address_id}/rescan"
        )
    assert rescan_resp.status_code == 200

    mock_ping.assert_not_called()

    addresses = db.get_addresses_by_subnet(subnet_id)
    addr = next(a for a in addresses if a["address"] == reserved_address)
    assert addr["status"] == "reserved"
