def test_default_concurrency_limit_is_32(client):
    res = client.get("/api/ipam/settings")
    assert res.status_code == 200
    assert res.json()["scanConcurrencyLimit"] == 32


def test_update_concurrency_limit(client):
    res = client.put("/api/ipam/settings", json={"scanConcurrencyLimit": 8})
    assert res.status_code == 200
    assert res.json()["scanConcurrencyLimit"] == 8
    res2 = client.get("/api/ipam/settings")
    assert res2.json()["scanConcurrencyLimit"] == 8


def test_update_rejects_value_below_minimum(client):
    res = client.put("/api/ipam/settings", json={"scanConcurrencyLimit": 0})
    assert res.status_code == 400


def test_update_rejects_value_above_maximum(client):
    res = client.put("/api/ipam/settings", json={"scanConcurrencyLimit": 9999})
    assert res.status_code == 400


def test_scan_respects_concurrency_limit(client, monkeypatch):
    import time
    import threading
    import ipam_scan

    max_concurrent = {"value": 0}
    current = {"value": 0}
    lock = threading.Lock()

    def fake_ping_host(address, timeout_seconds, attempts):
        with lock:
            current["value"] += 1
            max_concurrent["value"] = max(max_concurrent["value"], current["value"])
        time.sleep(0.1)
        with lock:
            current["value"] -= 1
        return False

    monkeypatch.setattr(ipam_scan, "ping_host", fake_ping_host)

    client.put("/api/ipam/settings", json={"scanConcurrencyLimit": 3})

    create_res = client.post("/api/ipam/subnets", json={"cidr": "10.55.0.0/28"})
    subnet_id = create_res.json()["id"]

    client.post(f"/api/ipam/subnets/{subnet_id}/autodiscover")

    assert max_concurrent["value"] <= 3