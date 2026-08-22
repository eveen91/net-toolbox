import os
import tempfile

import pytest

import troubleshoot_devices


@pytest.fixture
def devices_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(troubleshoot_devices, "DB_PATH", path)
    troubleshoot_devices.init_db()
    yield path
    os.remove(path)


def test_add_and_list_device(devices_db):
    result = troubleshoot_devices.add_device(
        "sw01", "10.0.0.2", "Cisco", "C9300", "17.9", "cisco_ios"
    )
    assert len(result) == 1
    dev = result[0]
    assert dev["name"] == "sw01"
    assert dev["mgmtIp"] == "10.0.0.2"
    assert dev["vendor"] == "Cisco"
    assert dev["model"] == "C9300"
    assert dev["osVersion"] == "17.9"
    assert dev["deviceType"] == "cisco_ios"
    assert dev["updatedAt"]


def test_add_device_os_version_optional(devices_db):
    result = troubleshoot_devices.add_device(
        "fw01", "10.0.0.1", "Checkpoint", "8600", None, "checkpoint_gaia"
    )
    assert result[0]["osVersion"] is None


def test_add_duplicate_device_raises(devices_db):
    troubleshoot_devices.add_device("sw01", "10.0.0.2", "Cisco", "C9300", None, "cisco_ios")
    with pytest.raises(ValueError, match='Device "sw01" already exists'):
        troubleshoot_devices.add_device(
            "sw01", "10.0.0.3", "Cisco", "C9300", None, "cisco_ios"
        )


def test_list_devices_sorted_case_insensitively(devices_db):
    troubleshoot_devices.add_device(
        "switch-b", "10.0.0.3", "Aruba", "8325", None, "aruba_aoscx"
    )
    troubleshoot_devices.add_device(
        "Switch-a", "10.0.0.2", "Cisco", "C9300", None, "cisco_ios"
    )
    names = [d["name"] for d in troubleshoot_devices.list_devices()]
    assert names == ["Switch-a", "switch-b"]


def test_list_devices_empty(devices_db):
    assert troubleshoot_devices.list_devices() == []


def test_update_device(devices_db):
    troubleshoot_devices.add_device("sw01", "10.0.0.2", "Cisco", "C9300", None, "cisco_ios")
    dev = troubleshoot_devices.list_devices()[0]
    result = troubleshoot_devices.update_device(
        dev["id"], "sw01", "10.0.0.9", "Cisco", "C9300", "17.12", "cisco_ios"
    )
    assert result[0]["mgmtIp"] == "10.0.0.9"
    assert result[0]["osVersion"] == "17.12"


def test_delete_device(devices_db):
    troubleshoot_devices.add_device("sw01", "10.0.0.2", "Cisco", "C9300", None, "cisco_ios")
    troubleshoot_devices.add_device("sw02", "10.0.0.3", "Cisco", "C9300", None, "cisco_ios")
    dev = troubleshoot_devices.list_devices()[0]
    result = troubleshoot_devices.delete_device(dev["id"])
    assert len(result) == 1
    assert result[0]["name"] != dev["name"]
