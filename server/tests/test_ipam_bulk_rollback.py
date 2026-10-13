import db


def _subnet(client, cidr):
    return client.post("/api/ipam/subnets", json={"cidr": cidr}).json()["id"]


def _address(client, subnet_id, address):
    client.post(f"/api/ipam/subnets/{subnet_id}/addresses", json={"address": address, "status": "used"})
    return next(row["id"] for row in db.get_addresses_by_subnet(subnet_id) if row["address"] == address)


def test_bulk_update_rolls_back_when_update_fails(client, monkeypatch):
    subnet_id = _subnet(client, "10.90.0.0/24")
    address_ids = [_address(client, subnet_id, "10.90.0.10"), _address(client, subnet_id, "10.90.0.11")]
    original = db.get_connection

    class ConnectionProxy:
        def __init__(self, connection): self.connection = connection
        def execute(self, statement, params=()):
            if statement.lstrip().startswith("UPDATE ipam_addresses"):
                raise RuntimeError("simulated update failure")
            return self.connection.execute(statement, params)
        def __getattr__(self, name): return getattr(self.connection, name)

    monkeypatch.setattr(db, "get_connection", lambda: ConnectionProxy(original()))
    try:
        db.bulk_update_addresses(subnet_id, address_ids, {"status": "reserved"})
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected simulated update failure")
    assert {row["status"] for row in db.get_addresses_by_subnet(subnet_id)} == {"used"}


def test_bulk_delete_rolls_back_archives_when_delete_fails(client, monkeypatch):
    subnet_id = _subnet(client, "10.91.0.0/24")
    address_ids = [_address(client, subnet_id, "10.91.0.10"), _address(client, subnet_id, "10.91.0.11")]
    original = db.get_connection

    class ConnectionProxy:
        def __init__(self, connection): self.connection = connection
        def execute(self, statement, params=()):
            if statement.lstrip().startswith("DELETE FROM ipam_addresses"):
                raise RuntimeError("simulated delete failure")
            return self.connection.execute(statement, params)
        def __getattr__(self, name): return getattr(self.connection, name)

    monkeypatch.setattr(db, "get_connection", lambda: ConnectionProxy(original()))
    try:
        db.bulk_delete_addresses(subnet_id, address_ids, "test")
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected simulated delete failure")
    assert {row["id"] for row in db.get_addresses_by_subnet(subnet_id)} == set(address_ids)
    assert db.list_archives("address") == []


def test_bulk_dhcp_move_rolls_back_when_second_audit_write_fails(client, monkeypatch):
    source_id = _subnet(client, "10.92.0.0/24")
    target_id = _subnet(client, "10.92.0.0/16")
    first = client.post(f"/api/ipam/subnets/{source_id}/dhcp-pools", json={"start_ip": "10.92.0.10", "end_ip": "10.92.0.20"}).json()
    second = client.post(f"/api/ipam/subnets/{source_id}/dhcp-pools", json={"start_ip": "10.92.0.30", "end_ip": "10.92.0.40"}).json()
    original_log = db._log_entity_change
    calls = 0

    def fail_second_log(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated audit failure")
        return original_log(*args, **kwargs)

    monkeypatch.setattr(db, "_log_entity_change", fail_second_log)
    try:
        db.bulk_move_dhcp_pools([first["id"], second["id"]], target_id)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected simulated audit failure")
    assert {pool["id"] for pool in db.get_dhcp_pools(source_id)} == {first["id"], second["id"]}
    assert db.get_dhcp_pools(target_id) == []
