import json
from unittest.mock import patch

import ipam_scan


def test_scan_workflow_streams_progress_and_persists_discovery(client):
    subnet = client.post("/api/ipam/subnets", json={"cidr": "10.60.0.0/29"}).json()

    def ping_host(address, *args, **kwargs):
        return address == "10.60.0.3"

    with patch.object(ipam_scan, "ping_host", side_effect=ping_host), patch.object(
        ipam_scan, "reverse_dns", return_value="scanner-e2e"
    ):
        start = client.post(f"/api/ipam/subnets/{subnet['id']}/autodiscover/start")
        assert start.status_code == 200
        job_id = start.json()["jobId"]
        events = []
        with client.stream("GET", f"/api/ipam/subnets/{subnet['id']}/autodiscover/stream/{job_id}") as response:
            assert response.status_code == 200
            for line in response.iter_lines():
                if line.startswith("data: "):
                    event = json.loads(line[6:])
                    events.append(event)
                    if event["status"] != "running":
                        break

    assert events
    assert events[-1]["status"] == "done"
    assert events[-1]["completed"] == events[-1]["total"]
    assert events[-1]["result"]["usedCount"] == 1
    addresses = client.get(f"/api/ipam/subnets/{subnet['id']}/addresses").json()["addresses"]
    assert any(address["address"] == "10.60.0.3" and address["hostname"] == "scanner-e2e" for address in addresses)
