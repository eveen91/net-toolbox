"""Exercise shared scan state through genuinely independent Python processes."""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import db

SERVER = Path(__file__).resolve().parents[1]


def worker(code, *args):
    result = subprocess.run([sys.executable, "-c", code, *map(str, args)], cwd=SERVER, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_concurrent_processes_cannot_claim_same_subnet(client):
    subnet = db.create_subnet("10.200.0.0/29")
    code = '''import db, sys, json
from pathlib import Path
db.DB_PATH = Path(sys.argv[1])
print(json.dumps(db.create_scan_job(sys.argv[3], int(sys.argv[2]))))
'''
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda name: worker(code, db.DB_PATH, subnet["id"], name), ["worker-one", "worker-two"]))
    assert sorted(results) == [False, True]
    job = db.get_active_scan_job(subnet["id"])
    db.update_scan_job(job["id"], status="done")
    assert worker(code, db.DB_PATH, subnet["id"], "worker-three") is True


def test_second_worker_startup_observes_progress_cancels_and_blocks_rescan(client, tmp_path):
    subnet = db.create_subnet("10.201.0.0/29")
    address = db.add_address(subnet["id"], "10.201.0.1")
    address_id = db.get_addresses_by_subnet(subnet["id"])[0]["id"]
    assert db.create_scan_job("owner-job", subnet["id"])
    db.update_scan_job("owner-job", completed=2, total=6)
    code = '''import sys, json
from pathlib import Path
import db, auth_db, troubleshoot_devices, troubleshoot_audit, main, ipam_scan
from fastapi.testclient import TestClient
db.DB_PATH = Path(sys.argv[1])
auth_db.AUTH_DB_PATH = Path(sys.argv[2])
troubleshoot_devices.DB_PATH = db.DB_PATH
troubleshoot_audit.DB_PATH = db.DB_PATH
ipam_scan.scan_one = lambda *args: (_ for _ in ()).throw(AssertionError("must not scan"))
with TestClient(main.app, headers={"X-CSRF-TOKEN": "fixed-csrf-token"}) as client:
    base = f"/api/ipam/subnets/{sys.argv[3]}"
    status = client.get(base + "/autodiscover/jobs/owner-job").json()
    rescan = client.post(base + f"/addresses/{sys.argv[4]}/rescan")
    cancel = client.post(base + "/autodiscover/jobs/owner-job/cancel")
    print(json.dumps({"status": status, "rescan": rescan.status_code, "cancel": cancel.status_code}))
'''
    result = worker(code, db.DB_PATH, tmp_path / "worker-auth.db", subnet["id"], address_id)
    assert result["status"]["status"] == "running"
    assert result["status"]["completed"] == 2
    assert result["rescan"] == 409
    assert result["cancel"] == 200
    assert db.is_scan_job_cancel_requested("owner-job")


def test_terminal_scan_cannot_be_revived_by_old_worker(client):
    subnet = db.create_subnet("10.202.0.0/29")
    assert db.create_scan_job("expired-job", subnet["id"])
    db.update_scan_job("expired-job", status="error", error="Scan timed out")
    db.update_scan_job("expired-job", completed=10, status="done", result={"late": True})
    job = db.get_scan_job("expired-job")
    assert job["status"] == "error"
    assert job["completed"] == 0
    assert job["result"] is None


def test_remote_cancellation_stops_owner_before_persisting_scan_results(client, monkeypatch):
    import threading
    import ipam_scan

    started, release = threading.Event(), threading.Event()
    subnet = db.create_subnet("10.203.0.0/30")

    def probe(address, *args):
        started.set()
        assert release.wait(15)
        return {"address": address, "alive": True, "hostname": "must-not-persist"}

    monkeypatch.setattr(ipam_scan, "scan_one", probe)
    start = client.post(f"/api/ipam/subnets/{subnet['id']}/autodiscover/start")
    assert start.status_code == 200
    job_id = start.json()["jobId"]
    assert started.wait(5)
    code = '''import sys, json
from pathlib import Path
import db
from ipam import scan_service
from ipam.repository import IpamRepository
db.DB_PATH = Path(sys.argv[1])
scan_service.configure(IpamRepository(db))
print(json.dumps(scan_service.cancel_autodiscover_job(int(sys.argv[2]), sys.argv[3])))
'''
    try:
        assert worker(code, db.DB_PATH, subnet["id"], job_id)["cancelRequested"]
    finally:
        release.set()
    stream = client.get(f"/api/ipam/subnets/{subnet['id']}/autodiscover/stream/{job_id}")
    assert '"status": "cancelled"' in stream.text
    assert not db.get_addresses_by_subnet(subnet["id"])
    assert db.get_active_scan_job(subnet["id"]) is None
