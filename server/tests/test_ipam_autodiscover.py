from unittest.mock import patch

import ipam_scan


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