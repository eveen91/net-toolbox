from unittest.mock import patch

import ipam_scan


def test_dashboard_includes_all_subnets(client):
    cidrs = ["10.0.0.0/29", "10.0.1.0/29", "10.0.2.0/29"]
    created_ids = []
    for cidr in cidrs:
        resp = client.post("/api/ipam/subnets", json={"cidr": cidr})
        assert resp.status_code == 200
        created_ids.append(resp.json()["id"])

    dashboard_resp = client.get("/api/ipam/dashboard")
    assert dashboard_resp.status_code == 200
    entries = dashboard_resp.json()

    entry_ids = [e["id"] for e in entries]
    for subnet_id in created_ids:
        assert subnet_id in entry_ids


def test_dashboard_shows_null_last_scan_for_unscanned_subnet(client):
    create_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/29"})
    assert create_resp.status_code == 200
    subnet_id = create_resp.json()["id"]

    dashboard_resp = client.get("/api/ipam/dashboard")
    assert dashboard_resp.status_code == 200
    entry = next(e for e in dashboard_resp.json() if e["id"] == subnet_id)

    assert entry["lastScannedAt"] is None
    assert entry["lastScanNewlyUsed"] is None
    assert entry["lastScanWentQuiet"] is None
    assert entry["lastScanHostnameChanged"] is None


def test_dashboard_shows_last_scan_data_after_scanning(client):
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

    dashboard_resp = client.get("/api/ipam/dashboard")
    assert dashboard_resp.status_code == 200
    entry = next(e for e in dashboard_resp.json() if e["id"] == subnet_id)

    assert entry["lastScannedAt"] is not None
    assert isinstance(entry["lastScanNewlyUsed"], int) and entry["lastScanNewlyUsed"] >= 0
    assert isinstance(entry["lastScanWentQuiet"], int) and entry["lastScanWentQuiet"] >= 0
    assert (
        isinstance(entry["lastScanHostnameChanged"], int)
        and entry["lastScanHostnameChanged"] >= 0
    )


def test_dashboard_reflects_second_scan_not_first(client):
    create_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/29"})
    assert create_resp.status_code == 200
    subnet_id = create_resp.json()["id"]

    first_target = "10.0.0.3"
    second_target = "10.0.0.4"

    def fake_ping_first(address, *args, **kwargs):
        return address == first_target

    with patch.object(ipam_scan, "ping_host", side_effect=fake_ping_first), \
         patch.object(ipam_scan, "reverse_dns", return_value=None):
        first_scan_resp = client.post(f"/api/ipam/subnets/{subnet_id}/autodiscover")
    assert first_scan_resp.status_code == 200
    assert first_target in first_scan_resp.json()["diff"]["newlyUsed"]

    def fake_ping_second(address, *args, **kwargs):
        return address == second_target

    with patch.object(ipam_scan, "ping_host", side_effect=fake_ping_second), \
         patch.object(ipam_scan, "reverse_dns", return_value=None):
        second_scan_resp = client.post(f"/api/ipam/subnets/{subnet_id}/autodiscover")
    assert second_scan_resp.status_code == 200
    second_scan_json = second_scan_resp.json()

    # first_target flips back to free (no longer pinged as alive) and
    # second_target newly appears -- so the two scans' diffs differ.
    assert second_target in second_scan_json["diff"]["newlyUsed"]
    assert first_target not in second_scan_json["diff"]["newlyUsed"]

    history_resp = client.get(f"/api/ipam/subnets/{subnet_id}/scans")
    assert history_resp.status_code == 200
    history = history_resp.json()
    second_history_entry = next(h for h in history if h["id"] == second_scan_json["scanId"])

    dashboard_resp = client.get("/api/ipam/dashboard")
    assert dashboard_resp.status_code == 200
    entry = next(e for e in dashboard_resp.json() if e["id"] == subnet_id)

    # The dashboard should reflect the second scan's data, not the first's.
    assert entry["lastScannedAt"] == second_history_entry["finishedAt"]
    assert entry["lastScanNewlyUsed"] == second_history_entry["newlyUsedCount"]
    assert entry["lastScanWentQuiet"] == second_history_entry["wentQuietCount"]
    assert entry["lastScanHostnameChanged"] == second_history_entry["hostnameChangedCount"]
    assert entry["lastScanNewlyUsed"] == 1
    assert entry["lastScanWentQuiet"] == 1