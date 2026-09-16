import time
from unittest.mock import patch

import db
import ipam_scan


def _wait_for_terminal_job(job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = db.get_scan_job(job_id)
        if job and job["status"] != "running":
            return job
        time.sleep(0.05)
    raise AssertionError(f"Scan job {job_id} did not reach a terminal state")


def test_scan_job_can_be_cancelled(client):
    subnet_id = client.post("/api/ipam/subnets", json={"cidr": "10.130.0.0/29"}).json()["id"]

    def slow_ping_host(*args, **kwargs):
        time.sleep(0.2)
        return False

    with patch.object(ipam_scan, "ping_host", side_effect=slow_ping_host), patch.object(
        ipam_scan, "reverse_dns", return_value=None
    ):
        start = client.post(f"/api/ipam/subnets/{subnet_id}/autodiscover/start")
        assert start.status_code == 200
        job_id = start.json()["jobId"]

        cancel = client.post(f"/api/ipam/subnets/{subnet_id}/autodiscover/jobs/{job_id}/cancel")
        assert cancel.status_code == 200
        assert cancel.json()["cancelRequested"] is True

        job = _wait_for_terminal_job(job_id)
        assert job["status"] == "cancelled"
        assert job["error"] == "Scan cancelled"
        assert db.get_active_scan_job(subnet_id) is None


def test_completed_scan_job_can_be_retried(client):
    subnet_id = client.post("/api/ipam/subnets", json={"cidr": "10.131.0.0/29"}).json()["id"]

    with patch.object(ipam_scan, "ping_host", return_value=False), patch.object(
        ipam_scan, "reverse_dns", return_value=None
    ):
        start = client.post(f"/api/ipam/subnets/{subnet_id}/autodiscover/start")
        first_job = _wait_for_terminal_job(start.json()["jobId"])
        assert first_job["status"] == "done"

        retry = client.post(
            f"/api/ipam/subnets/{subnet_id}/autodiscover/jobs/{first_job['id']}/retry"
        )
        assert retry.status_code == 200
        assert retry.json()["jobId"] != first_job["id"]
        second_job = _wait_for_terminal_job(retry.json()["jobId"])
        assert second_job["status"] == "done"


def test_scan_schedule_and_timeout_cleanup(client):
    subnet = db.create_subnet("10.132.0.0/29")
    schedule = db.upsert_scan_schedule(subnet["id"], 15, enabled=True)
    assert schedule["intervalMinutes"] == 15
    assert schedule["enabled"] is True
    assert schedule["nextRunAt"] is not None

    assert db.create_scan_job("expired-job", subnet["id"])
    conn = db.get_connection()
    try:
        conn.execute("UPDATE ipam_scan_jobs SET updated_at = '2000-01-01T00:00:00+00:00' WHERE id = 'expired-job'")
        conn.commit()
    finally:
        conn.close()

    db.expire_timed_out_scan_jobs(timeout_seconds=1)
    job = db.get_scan_job("expired-job")
    assert job["status"] == "error"
    assert job["error"] == "Scan timed out"
