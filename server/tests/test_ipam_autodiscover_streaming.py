import json
from unittest.mock import patch

import ipam_scan
import main


def test_start_job_returns_job_id(client):
    create_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/29"})
    assert create_resp.status_code == 200
    subnet_id = create_resp.json()["id"]

    with patch.object(ipam_scan, "ping_host", return_value=False), \
         patch.object(ipam_scan, "reverse_dns", return_value=None):
        start_resp = client.post(f"/api/ipam/subnets/{subnet_id}/autodiscover/start")
    assert start_resp.status_code == 200
    job_id = start_resp.json()["jobId"]
    assert isinstance(job_id, str)
    assert len(job_id) > 0

    main.SCANS_IN_PROGRESS.discard(subnet_id)


def test_stream_reports_final_done_status(client):
    create_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/29"})
    assert create_resp.status_code == 200
    subnet_id = create_resp.json()["id"]

    def fake_ping_host(address, *args, **kwargs):
        return address.endswith(".3")

    def fake_reverse_dns(address, *args, **kwargs):
        return "myhost.local" if address.endswith(".3") else None

    with patch.object(ipam_scan, "ping_host", side_effect=fake_ping_host), \
         patch.object(ipam_scan, "reverse_dns", side_effect=fake_reverse_dns):
        start_resp = client.post(f"/api/ipam/subnets/{subnet_id}/autodiscover/start")
        assert start_resp.status_code == 200
        job_id = start_resp.json()["jobId"]

        final_event = None
        with client.stream(
            "GET", f"/api/ipam/subnets/{subnet_id}/autodiscover/stream/{job_id}"
        ) as stream_resp:
            assert stream_resp.status_code == 200
            for line in stream_resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                event = json.loads(line[len("data: "):])
                if event["status"] in ("done", "error") and "result" in event:
                    final_event = event
                    break

    assert final_event is not None
    assert final_event["status"] == "done"
    result = final_event["result"]
    assert result is not None

    # Cross-check against the shape/values of the existing blocking endpoint
    # by running an equivalent scan on a fresh, identically-shaped subnet.
    create_resp2 = client.post("/api/ipam/subnets", json={"cidr": "10.0.1.0/29"})
    assert create_resp2.status_code == 200
    subnet_id2 = create_resp2.json()["id"]
    with patch.object(ipam_scan, "ping_host", side_effect=fake_ping_host), \
         patch.object(ipam_scan, "reverse_dns", side_effect=fake_reverse_dns):
        blocking_resp = client.post(f"/api/ipam/subnets/{subnet_id2}/autodiscover")
    assert blocking_resp.status_code == 200
    blocking_json = blocking_resp.json()

    assert set(result.keys()) == set(blocking_json.keys())
    assert result["scannedCount"] == blocking_json["scannedCount"]
    assert result["usedCount"] == blocking_json["usedCount"]
    assert result["freeCount"] == blocking_json["freeCount"]
    assert result["skippedCount"] == blocking_json["skippedCount"]
    assert set(result["diff"].keys()) == set(blocking_json["diff"].keys())
    assert len(result["diff"]["newlyUsed"]) == len(blocking_json["diff"]["newlyUsed"])
    assert len(result["diff"]["wentQuiet"]) == len(blocking_json["diff"]["wentQuiet"])
    assert len(result["diff"]["hostnameChanged"]) == len(blocking_json["diff"]["hostnameChanged"])


def test_stream_unknown_job_returns_404(client):
    resp = client.get("/api/ipam/subnets/1/autodiscover/stream/not-a-real-job-id")
    assert resp.status_code == 404


def test_start_job_rejects_while_subnet_already_scanning(client):
    create_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/29"})
    assert create_resp.status_code == 200
    subnet_id = create_resp.json()["id"]

    main.SCANS_IN_PROGRESS.add(subnet_id)
    try:
        start_resp = client.post(f"/api/ipam/subnets/{subnet_id}/autodiscover/start")
        assert start_resp.status_code == 409
    finally:
        main.SCANS_IN_PROGRESS.discard(subnet_id)