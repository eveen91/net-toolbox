import pytest

import troubleshoot_logic
import troubleshoot_devices
from device_drivers import get_driver


class FakeSession:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


def test_get_driver_known_and_unknown():
    for device_type in ("cisco_ios", "aruba_aoscx", "checkpoint_gaia"):
        assert get_driver(device_type) is not None
    with pytest.raises(ValueError, match="Unknown device_type"):
        get_driver("some_vendor")


def test_resolve_ip_to_mac(monkeypatch):
    arp_text = "10.0.0.15. 00:1a:2b:3c:4d:5e.\n"

    class D:
        def get_arp_table(self, session):
            return arp_text

    monkeypatch.setattr(troubleshoot_logic, "DeviceSession", FakeSession)
    monkeypatch.setattr(troubleshoot_logic, "get_driver", lambda dt: D())
    gateway = {"deviceType": "checkpoint_gaia", "mgmtIp": "10.0.0.1"}

    assert (
        troubleshoot_logic.resolve_ip_to_mac("10.0.0.15", gateway, "u", "p")
        == "00:1a:2b:3c:4d:5e"
    )
    assert troubleshoot_logic.resolve_ip_to_mac("10.0.0.99", gateway, "u", "p") is None


def test_locate_mac_on_switches_finds_cisco_match(monkeypatch):
    mac = "00:11:22:33:44:55"
    devices = [
        {"deviceType": "aruba_aoscx", "name": "sw1", "mgmtIp": "10.0.0.2"},
        {"deviceType": "cisco_ios", "name": "sw2", "mgmtIp": "10.0.0.3"},
    ]
    cisco_table = """Vlan   Mac Address      Type      Ports
----   -----------      --------  -----
10     0011.2233.4455   DYNAMIC   Gi1/0/12
"""
    aruba_table = """MAC Address     VLAN  Type     Port
00:11:22:33:44:66 10 dynamic 1/1/12
"""

    def fake_get_driver(device_type):
        class D:
            def get_mac_table(self, session):
                return cisco_table if device_type == "cisco_ios" else aruba_table

        return D()

    monkeypatch.setattr(troubleshoot_logic, "DeviceSession", FakeSession)
    monkeypatch.setattr(troubleshoot_logic, "get_driver", fake_get_driver)

    result = troubleshoot_logic.locate_mac_on_switches(mac, devices, "u", "p")
    assert result == {"device": "sw2", "port": "Gi1/0/12", "vlan": "10"}


def test_locate_mac_on_switches_skips_unreachable_switch(monkeypatch):
    mac = "00:11:22:33:44:55"
    devices = [
        {"deviceType": "cisco_ios", "name": "bad", "mgmtIp": "10.0.0.99"},
        {"deviceType": "cisco_ios", "name": "good", "mgmtIp": "10.0.0.3"},
    ]

    class Bad:
        def get_mac_table(self, session):
            raise RuntimeError("unreachable")

    class Good:
        def get_mac_table(self, session):
            return "Vlan Mac Address Type Ports\n10 0011.2233.4455 DYNAMIC Gi1/0/12\n"

    drivers = iter([Bad(), Good()])

    def fake_get_driver(device_type):
        return next(drivers)

    monkeypatch.setattr(troubleshoot_logic, "DeviceSession", FakeSession)
    monkeypatch.setattr(troubleshoot_logic, "get_driver", fake_get_driver)

    result = troubleshoot_logic.locate_mac_on_switches(mac, devices, "u", "p")
    assert result == {"device": "good", "port": "Gi1/0/12", "vlan": "10"}


def test_locate_mac_on_switches_no_match_returns_none(monkeypatch):
    mac = "00:11:22:33:44:55"
    devices = [{"deviceType": "cisco_ios", "name": "sw1", "mgmtIp": "10.0.0.3"}]

    class D:
        def get_mac_table(self, session):
            return "Vlan Mac Address Type Ports\n10 0011.2233.4499 DYNAMIC Gi1/0/12\n"

    monkeypatch.setattr(troubleshoot_logic, "DeviceSession", FakeSession)
    monkeypatch.setattr(troubleshoot_logic, "get_driver", lambda dt: D())

    assert troubleshoot_logic.locate_mac_on_switches(mac, devices, "u", "p") is None


def test_get_port_health_cisco(monkeypatch):
    class D:
        def get_interface_status(self, session, port):
            return (
                "GigabitEthernet1/0/12 is up, line protocol is up (connected)\n"
                " Full-duplex, 1000Mb/s, media type is 10/100/1000BaseTX\n"
            )

        def get_interface_errors(self, session, port):
            return "Port Align-Err FCS-Err Xmit-Err Rcv-Err UnderSize OutDiscards\nGi1/0/12 0 0 0 0 0 0\n"

    monkeypatch.setattr(troubleshoot_logic, "DeviceSession", FakeSession)
    monkeypatch.setattr(troubleshoot_logic, "get_driver", lambda dt: D())
    device = {"deviceType": "cisco_ios", "mgmtIp": "10.0.0.3"}

    result = troubleshoot_logic.get_port_health(device, "Gi1/0/12", "u", "p")
    assert result == {
        "adminStatus": "up",
        "operStatus": "up",
        "speed": "1000Mb/s",
        "duplex": "Full",
        "inputErrors": 0,
        "outputErrors": 0,
        "crcErrors": 0,
    }


def test_get_route_check(monkeypatch):
    class D:
        def get_route(self, session, ip):
            return "via 10.0.0.1, eth0"

    monkeypatch.setattr(troubleshoot_logic, "DeviceSession", FakeSession)
    monkeypatch.setattr(troubleshoot_logic, "get_driver", lambda dt: D())
    gateway = {"deviceType": "checkpoint_gaia", "mgmtIp": "10.0.0.1"}

    assert troubleshoot_logic.get_route_check("8.8.8.8", gateway, "u", "p") == {
        "nextHop": "10.0.0.1",
        "interface": "eth0",
    }


def test_get_stp_report_all_skips_unsupported_and_sorts(monkeypatch):
    devices = [
        {"deviceType": "checkpoint_gaia", "name": "fw"},
        {"deviceType": "cisco_ios", "name": "sw1"},
        {"deviceType": "aruba_aoscx", "name": "sw2"},
    ]

    def fake_report(device, username, password):
        if device["name"] == "sw1":
            return [
                {"port": "Gi1/0/1", "topologyChanges": 3, "lastChangeAgo": "0:02:15", "device": "sw1", "lastChangeSeconds": 135},
                {"port": "Gi1/0/2", "topologyChanges": 8, "lastChangeAgo": "0:00:30", "device": "sw1", "lastChangeSeconds": 30},
            ]
        return [
            {"port": "1/1/1", "topologyChanges": 5, "lastChangeAgo": "0:01:00", "device": "sw2", "lastChangeSeconds": 60},
        ]

    monkeypatch.setattr(troubleshoot_logic, "get_stp_report_for_device", fake_report)
    entries = troubleshoot_logic.get_stp_report_all(devices, "u", "p")
    assert [e["port"] for e in entries] == ["Gi1/0/2", "1/1/1", "Gi1/0/1"]


def test_get_stp_report_all_skips_raising_device(monkeypatch):
    def fake_report(device, username, password):
        raise RuntimeError("unreachable")

    monkeypatch.setattr(troubleshoot_logic, "get_stp_report_for_device", fake_report)
    devices = [{"deviceType": "cisco_ios", "name": "sw1"}]
    assert troubleshoot_logic.get_stp_report_all(devices, "u", "p") == []


def _monkeypatch_devices(monkeypatch, devices):
    monkeypatch.setattr(troubleshoot_devices, "list_devices", lambda: devices)


def test_run_full_diagnostic_success(monkeypatch):
    devices = [
        {"deviceType": "checkpoint_gaia", "name": "fw", "mgmtIp": "10.0.0.1"},
        {"deviceType": "cisco_ios", "name": "sw1", "mgmtIp": "10.0.0.3"},
    ]
    _monkeypatch_devices(monkeypatch, devices)
    monkeypatch.setattr(
        troubleshoot_logic, "ping_host",
        lambda ip: "4 packets transmitted, 4 received, 0% packet loss, time 3005ms\n"
        "rtt min/avg/max/mdev = 12.345/13.456/15.678/1.234 ms\n",
    )
    monkeypatch.setattr(
        troubleshoot_logic, "get_route_check",
        lambda ip, gateway, u, p: {"nextHop": "10.0.0.1", "interface": "eth0"},
    )
    monkeypatch.setattr(
        troubleshoot_logic, "resolve_ip_to_mac",
        lambda ip, gateway, u, p: "00:1a:2b:3c:4d:5e",
    )
    monkeypatch.setattr(
        troubleshoot_logic, "locate_mac_on_switches",
        lambda mac, switches, u, p: {"device": "sw1", "port": "Gi1/0/12", "vlan": "10"},
    )
    monkeypatch.setattr(
        troubleshoot_logic, "get_port_health",
        lambda device, port, u, p: {
            "adminStatus": "up", "operStatus": "up", "speed": "1000Mb/s",
            "duplex": "Full", "inputErrors": 0, "outputErrors": 0, "crcErrors": 0,
        },
    )
    monkeypatch.setattr(
        troubleshoot_logic, "get_transceiver_health",
        lambda device, port, u, p: {"temperature": {"value": 32.5, "status": "ok"}},
    )
    monkeypatch.setattr(
        troubleshoot_logic, "get_port_access_status",
        lambda device, port, u, p: {"enabled": True, "status": "Authenticated"},
    )

    result = troubleshoot_logic.run_full_diagnostic("10.0.0.15", "admin", "pw")
    assert result["ip"] == "10.0.0.15"
    assert result["ping"] == {"success": True, "packetsSent": 4, "packetsReceived": 4, "packetLossPercent": 0.0, "avgLatencyMs": 13.456}
    assert result["route"] == {"success": True, "nextHop": "10.0.0.1", "interface": "eth0"}
    assert result["locate"] == {"success": True, "mac": "00:1a:2b:3c:4d:5e", "device": "sw1", "port": "Gi1/0/12", "vlan": "10"}
    assert result["portHealth"]["success"] is True
    assert result["transceiverHealth"]["success"] is True
    assert result["accessStatus"]["success"] is True


def test_run_full_diagnostic_no_gateway(monkeypatch):
    _monkeypatch_devices(monkeypatch, [])
    monkeypatch.setattr(
        troubleshoot_logic, "ping_host",
        lambda ip: "4 packets transmitted, 4 received, 0% packet loss, time 3005ms\n"
        "rtt min/avg/max/mdev = 12.345/13.456/15.678/1.234 ms\n",
    )

    result = troubleshoot_logic.run_full_diagnostic("10.0.0.15", "admin", "pw")
    assert result["ping"]["success"] is True
    assert result["route"] == {"success": False, "error": "No gateway device configured"}
    assert result["locate"] == {"success": False, "error": "No gateway device configured"}
    assert result["portHealth"] is None
    assert result["transceiverHealth"] is None
    assert result["accessStatus"] is None


def test_run_full_diagnostic_ip_not_in_arp(monkeypatch):
    devices = [{"deviceType": "checkpoint_gaia", "name": "fw", "mgmtIp": "10.0.0.1"}]
    _monkeypatch_devices(monkeypatch, devices)
    monkeypatch.setattr(troubleshoot_logic, "ping_host", lambda ip: "0 packets transmitted")
    monkeypatch.setattr(
        troubleshoot_logic, "get_route_check",
        lambda ip, gateway, u, p: {"nextHop": "10.0.0.1", "interface": "eth0"},
    )
    monkeypatch.setattr(
        troubleshoot_logic, "resolve_ip_to_mac", lambda ip, gateway, u, p: None,
    )

    result = troubleshoot_logic.run_full_diagnostic("10.0.0.15", "admin", "pw")
    assert result["locate"] == {"success": False, "error": "IP not found in ARP table"}
    assert result["portHealth"] is None
    assert result["transceiverHealth"] is None
    assert result["accessStatus"] is None


def test_run_full_diagnostic_mac_not_on_switch(monkeypatch):
    devices = [
        {"deviceType": "checkpoint_gaia", "name": "fw", "mgmtIp": "10.0.0.1"},
        {"deviceType": "cisco_ios", "name": "sw1", "mgmtIp": "10.0.0.3"},
    ]
    _monkeypatch_devices(monkeypatch, devices)
    monkeypatch.setattr(troubleshoot_logic, "ping_host", lambda ip: "0 packets transmitted")
    monkeypatch.setattr(
        troubleshoot_logic, "get_route_check",
        lambda ip, gateway, u, p: {"nextHop": "10.0.0.1", "interface": "eth0"},
    )
    monkeypatch.setattr(
        troubleshoot_logic, "resolve_ip_to_mac", lambda ip, gateway, u, p: "00:1a:2b:3c:4d:5e",
    )
    monkeypatch.setattr(
        troubleshoot_logic, "locate_mac_on_switches", lambda mac, switches, u, p: None,
    )

    result = troubleshoot_logic.run_full_diagnostic("10.0.0.15", "admin", "pw")
    assert result["locate"] == {"success": False, "error": "MAC 00:1a:2b:3c:4d:5e not found on any switch"}
    assert result["portHealth"] is None
    assert result["transceiverHealth"] is None
    assert result["accessStatus"] is None


def test_run_full_diagnostic_ping_failure_is_isolated(monkeypatch):
    devices = [{"deviceType": "checkpoint_gaia", "name": "fw", "mgmtIp": "10.0.0.1"}]
    _monkeypatch_devices(monkeypatch, devices)

    def boom(ip):
        raise RuntimeError("ping binary missing")

    monkeypatch.setattr(troubleshoot_logic, "ping_host", boom)
    monkeypatch.setattr(
        troubleshoot_logic, "get_route_check",
        lambda ip, gateway, u, p: {"nextHop": "10.0.0.1", "interface": "eth0"},
    )

    result = troubleshoot_logic.run_full_diagnostic("10.0.0.15", "admin", "pw")
    assert result["ping"] == {"success": False, "error": "ping binary missing"}
    assert result["route"]["success"] is True
