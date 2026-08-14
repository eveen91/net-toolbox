import json
import time
from unittest.mock import patch

import ipam_scan
import main


def wait_for_job_done(job_id, timeout=5.0):
    """Poll SCAN_JOBS directly until the job leaves the 'running' state.

    Used to make sure a background scan job has fully finished (and thus
    cleaned up SCANS_IN_PROGRESS / SCAN_JOBS_BY_SUBNET) before a test ends,
    so it doesn't leak into the next test via the module-level registries.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = main.SCAN_JOBS.get(job_id)
        if job is None or job["status"] != "running":
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s")


def test_active_endpoint_returns_null_when_idle(client):
    create_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/29"})
    assert create_resp.status_code == 200
    subnet_id = create_resp.json()["id"]

    active_resp = client.get(f"/api/ipam/subnets/{subnet_id}/autodiscover/active")
    assert active_resp.status_code == 200
    assert active_resp.json()["jobId"] is None


def test_active_endpoint_returns_job_while_running(client):
    create_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/29"})
    assert create_resp.status_code == 200
    subnet_id = create_resp.json()["id"]

    def slow_ping_host(address, *args, **kwargs):
        time.sleep(0.2)
        return False

    with patch.object(ipam_scan, "ping_host", side_effect=slow_ping_host), \
         patch.object(ipam_scan, "reverse_dns", return_value=None):
        start_resp = client.post(f"/api/ipam/subnets/{subnet_id}/autodiscover/start")
        assert start_resp.status_code == 200
        job_id = start_resp.json()["jobId"]

        active_resp = client.get(f"/api/ipam/subnets/{subnet_id}/autodiscover/active")
        assert active_resp.status_code == 200
        active_json = active_resp.json()
        assert active_json["jobId"] == job_id
        assert "completed" in active_json
        assert "total" in active_json

        wait_for_job_done(job_id)


def test_active_endpoint_returns_null_after_completion(client):
    create_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/29"})
    assert create_resp.status_code == 200
    subnet_id = create_resp.json()["id"]

    def slow_ping_host(address, *args, **kwargs):
        time.sleep(0.2)
        return False

    with patch.object(ipam_scan, "ping_host", side_effect=slow_ping_host), \
         patch.object(ipam_scan, "reverse_dns", return_value=None):
        start_resp = client.post(f"/api/ipam/subnets/{subnet_id}/autodiscover/start")
        assert start_resp.status_code == 200
        job_id = start_resp.json()["jobId"]

        wait_for_job_done(job_id)

    active_resp = client.get(f"/api/ipam/subnets/{subnet_id}/autodiscover/active")
    assert active_resp.status_code == 200
    assert active_resp.json()["jobId"] is None


def test_stream_includes_address_statuses(client):
    create_resp = client.post("/api/ipam/subnets", json={"cidr": "10.0.0.0/29"})
    assert create_resp.status_code == 200
    subnet_id = create_resp.json()["id"]

    def slow_ping_host(address, *args, **kwargs):
        time.sleep(0.2)
        return address.endswith(".3")

    def fake_reverse_dns(address, *args, **kwargs):
        return "myhost.local" if address.endswith(".3") else None

    with patch.object(ipam_scan, "ping_host", side_effect=slow_ping_host), \
         patch.object(ipam_scan, "reverse_dns", side_effect=fake_reverse_dns):
        start_resp = client.post(f"/api/ipam/subnets/{subnet_id}/autodiscover/start")
        assert start_resp.status_code == 200
        job_id = start_resp.json()["jobId"]

        events = []
        with client.stream(
            "GET", f"/api/ipam/subnets/{subnet_id}/autodiscover/stream/{job_id}"
        ) as stream_resp:
            assert stream_resp.status_code == 200
            for line in stream_resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                event = json.loads(line[len("data: "):])
                events.append(event)
                if event["status"] in ("done", "error") and "result" in event:
                    break

    assert len(events) > 0

    non_empty_events = [e for e in events if e["addresses"]]
    assert len(non_empty_events) > 0

    sample_entry = non_empty_events[0]["addresses"][0]
    assert set(sample_entry.keys()) == {"address", "status", "alive", "hostname"}
    assert isinstance(sample_entry["address"], str)
    assert sample_entry["status"] in ("pending", "in_progress", "done")

    final_event = events[-1]
    assert final_event["status"] == "done"
    assert len(final_event["addresses"]) > 0
    for entry in final_event["addresses"]:
        assert entry["status"] == "done"
        assert entry["alive"] is not None