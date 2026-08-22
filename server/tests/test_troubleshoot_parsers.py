from troubleshoot_logic import (
    parse_arp_table,
    parse_mac_table_cisco,
    parse_mac_table_aruba,
    parse_interface_status_cisco,
    parse_interface_errors_cisco,
    parse_interface_status_aruba,
    parse_cable_diagnostics_cisco,
    parse_cable_diagnostics_aruba,
    parse_transceiver_cisco,
    parse_transceiver_aruba,
    evaluate_transceiver_health,
    parse_stp_detail_cisco,
    parse_stp_detail_aruba,
    stp_ago_to_seconds,
    parse_port_security_cisco,
    parse_port_access_aruba,
    parse_ping_output,
    parse_route_checkpoint,
    ping_host,
)


def test_parse_mac_table_cisco():
    sample = """
    Vlan   Mac Address   Type      Ports
    ----   -----------   --------  -----
    10     0011.2233.4455  DYNAMIC  Gi1/0/12
    """
    result = parse_mac_table_cisco(sample)
    assert len(result) == 1
    assert result[0]["mac"] == "00:11:22:33:44:55"
    assert result[0]["port"] == "Gi1/0/12"
    assert result[0]["vlan"] == "10"


def test_parse_interface_status_cisco():
    sample = """GigabitEthernet1/0/12 is up, line protocol is up (connected)
    Full-duplex, 1000Mb/s, media type is 10/100/1000BaseTX
"""
    result = parse_interface_status_cisco(sample)
    assert result["adminStatus"] == "up"
    assert result["operStatus"] == "up"
    assert result["duplex"] == "Full"
    assert result["speed"] == "1000Mb/s"


def test_parse_ping_output():
    sample = """4 packets transmitted, 4 received, 0% packet loss, time 3005ms
rtt min/avg/max/mdev = 12.345/13.456/15.678/1.234 ms
"""
    result = parse_ping_output(sample)
    assert result["packetsSent"] == 4
    assert result["packetsReceived"] == 4
    assert result["packetLossPercent"] == 0.0
    assert result["avgLatencyMs"] == 13.456


def test_parse_arp_table_lowercases_mac():
    sample = """10.0.0.15. 00:1a:2b:3c:4d:5e.
10.0.0.20. 00:1A:2B:3C:4D:5F.
"""
    result = parse_arp_table(sample)
    assert result == [
        {"ip": "10.0.0.15", "mac": "00:1a:2b:3c:4d:5e"},
        {"ip": "10.0.0.20", "mac": "00:1a:2b:3c:4d:5f"},
    ]


def test_parse_arp_table_empty():
    assert parse_arp_table("no arp entries here") == []


def test_parse_mac_table_aruba():
    sample = """MAC Address     VLAN  Type     Port
00:11:22:33:44:55 10 dynamic 1/1/12
00:11:22:33:44:66 20 dynamic 1/1/13
"""
    result = parse_mac_table_aruba(sample)
    assert result[0] == {"mac": "00:11:22:33:44:55", "vlan": "10", "port": "1/1/12"}
    assert result[1] == {"mac": "00:11:22:33:44:66", "vlan": "20", "port": "1/1/13"}


def test_parse_interface_errors_cisco():
    sample = """Port       Align-Err  FCS-Err   Xmit-Err  Rcv-Err   UnderSize  OutDiscards
Gi1/0/12   1          2         3         4         5          6
"""
    result = parse_interface_errors_cisco(sample)
    assert result == {
        "alignErr": 1,
        "fcsErr": 2,
        "xmitErr": 3,
        "rcvErr": 4,
        "underSize": 5,
        "outDiscards": 6,
    }


def test_parse_interface_errors_cisco_no_data():
    result = parse_interface_errors_cisco("no counters available")
    assert result == {
        "alignErr": None,
        "fcsErr": None,
        "xmitErr": None,
        "rcvErr": None,
        "underSize": None,
        "outDiscards": None,
    }


def test_parse_interface_status_aruba():
    sample = """Admin state is up
State information: up
Speed 1000,MTU 1500
  0 input packets. 0 input errors 0 CRC/FCS
  0 output packets. 0 output errors
"""
    result = parse_interface_status_aruba(sample)
    assert result["adminStatus"] == "up"
    assert result["operStatus"] == "up"
    assert result["speed"] == "1000Mb/s"
    assert result["duplex"] == "unknown"
    assert result["inputErrors"] == 0
    assert result["outputErrors"] == 0
    assert result["crcErrors"] == 0


def test_parse_cable_diagnostics_cisco():
    sample = """Gi1/0/12 1000M Pair A 0 +/- 10 meters Pair A Normal
  Pair B 0 +/- 10 meters Pair B Normal
  Pair C 0 +/- 10 meters Pair C Open
"""
    result = parse_cable_diagnostics_cisco(sample)
    assert result == [
        {"pair": "A", "lengthMeters": 0, "status": "Normal"},
        {"pair": "B", "lengthMeters": 0, "status": "Normal"},
        {"pair": "C", "lengthMeters": 0, "status": "Open"},
    ]


def test_parse_cable_diagnostics_cisco_empty():
    assert parse_cable_diagnostics_cisco("no tdr results") == []


def test_parse_cable_diagnostics_aruba():
    sample = """A OK 3 m
B OK 3 m
C Shorted 1 m
"""
    result = parse_cable_diagnostics_aruba(sample)
    assert result == [
        {"pair": "A", "status": "OK", "lengthMeters": 3},
        {"pair": "B", "status": "OK", "lengthMeters": 3},
        {"pair": "C", "status": "Shorted", "lengthMeters": 1},
    ]


def test_parse_cable_diagnostics_aruba_empty():
    assert parse_cable_diagnostics_aruba("no results") == []


def test_parse_transceiver_cisco():
    sample = """Temperature 32.50 C 75.00 C 70.00 C -5.00 C -10.00 C
Voltage 3.30 V 3.60 V 3.50 V 3.10 V 3.00 V
Bias current 6.60 mA 17.00 mA 14.00 mA 2.00 mA 1.00 mA
Tx Power -2.50 dBm -1.00 dBm -2.00 dBm -7.00 dBm -9.00 dBm
Rx Power -3.10 dBm -1.00 dBm -2.00 dBm -13.00 dBm -15.00 dBm
"""
    result = parse_transceiver_cisco(sample)
    assert result["temperature"] == {
        "value": 32.5,
        "highAlarm": 75.0,
        "highWarn": 70.0,
        "lowWarn": -5.0,
        "lowAlarm": -10.0,
    }
    assert result["voltage"] == {
        "value": 3.3,
        "highAlarm": 3.6,
        "highWarn": 3.5,
        "lowWarn": 3.1,
        "lowAlarm": 3.0,
    }
    assert result["biasCurrent"]["value"] == 6.6
    assert result["txPower"]["value"] == -2.5
    assert result["rxPower"]["value"] == -3.1


def test_parse_transceiver_cisco_no_data():
    result = parse_transceiver_cisco("transceiver not present")
    assert result == {
        "temperature": None,
        "voltage": None,
        "biasCurrent": None,
        "txPower": None,
        "rxPower": None,
    }


def test_parse_transceiver_aruba():
    sample = """Temperature: 32.5 C (Warning Low 0.0, Warning High 70.0, Alarm Low -5.0, Alarm High 75.0)
Voltage: 3.3 V (Warning Low 3.1, Warning High 3.5, Alarm Low 3.0, Alarm High 3.6)
Bias Current: 6.6 mA (Warning Low 2.0, Warning High 14.0, Alarm Low 1.0, Alarm High 17.0)
TX Power: -2.5 dBm (Warning Low -2.0, Warning High -1.0, Alarm Low -7.0, Alarm High -9.0)
RX Power: -3.1 dBm (Warning Low -2.0, Warning High -1.0, Alarm Low -13.0, Alarm High -15.0)
"""
    result = parse_transceiver_aruba(sample)
    assert result["temperature"] == {
        "value": 32.5,
        "lowWarn": 0.0,
        "highWarn": 70.0,
        "lowAlarm": -5.0,
        "highAlarm": 75.0,
    }
    assert result["txPower"] == {
        "value": -2.5,
        "lowWarn": -2.0,
        "highWarn": -1.0,
        "lowAlarm": -7.0,
        "highAlarm": -9.0,
    }
    assert result["rxPower"]["value"] == -3.1


def test_evaluate_transceiver_health_statuses():
    metrics = {
        "temperature": {"value": 60.0, "highAlarm": 75.0, "highWarn": 70.0, "lowWarn": -5.0, "lowAlarm": -10.0},
        "voltage": None,
        "biasCurrent": {"value": 17.0, "highAlarm": 17.0, "highWarn": 14.0, "lowWarn": 2.0, "lowAlarm": 1.0},
        "txPower": {"value": -2.0, "highAlarm": -1.0, "highWarn": -2.0, "lowWarn": -7.0, "lowAlarm": -9.0},
        "rxPower": {"value": -3.1, "highAlarm": -1.0, "highWarn": -2.0, "lowWarn": -13.0, "lowAlarm": -15.0},
    }
    result = evaluate_transceiver_health(metrics)
    assert result["temperature"]["status"] == "ok"
    assert result["voltage"] == {"value": None, "status": "unknown"}
    assert result["biasCurrent"]["status"] == "alarm"
    assert result["txPower"]["status"] == "warn"
    assert result["rxPower"]["status"] == "ok"


def test_parse_stp_detail_cisco():
    sample = """STP VLAN 10
Number of topology changes 3 last change occurred 0:02:15 ago
 from GigabitEthernet1/0/12
STP VLAN 20
Number of topology changes 1 last change occurred 0:01:00 ago
 from GigabitEthernet1/0/13
"""
    result = parse_stp_detail_cisco(sample)
    assert result == [
        {"port": "GigabitEthernet1/0/12", "topologyChanges": 3, "lastChangeAgo": "0:02:15"},
        {"port": "GigabitEthernet1/0/13", "topologyChanges": 1, "lastChangeAgo": "0:01:00"},
    ]


def test_parse_stp_detail_aruba():
    sample = """Port 1/1/12 - Topology changes: 3, last change 0:02:15 ago
Port 1/1/13 - Topology changes: 5, last change 0:01:00 ago
"""
    result = parse_stp_detail_aruba(sample)
    assert result == [
        {"port": "1/1/12", "topologyChanges": 3, "lastChangeAgo": "0:02:15"},
        {"port": "1/1/13", "topologyChanges": 5, "lastChangeAgo": "0:01:00"},
    ]


def test_stp_ago_to_seconds():
    assert stp_ago_to_seconds("0:02:15") == 135
    assert stp_ago_to_seconds("1:02:15") == 3735
    assert stp_ago_to_seconds("2:30") == 150
    assert stp_ago_to_seconds("garbage") == 999999
    assert stp_ago_to_seconds("a:b:c") == 999999


def test_parse_port_security_cisco_enabled():
    sample = """Port Security: Enabled
Port Status: Secure-up
"""
    result = parse_port_security_cisco(sample)
    assert result == {"enabled": True, "status": "Secure-up"}


def test_parse_port_security_cisco_disabled():
    sample = """Port Security: Disabled
Port Status: Secure-shutdown
"""
    result = parse_port_security_cisco(sample)
    assert result == {"enabled": False, "status": "Secure-shutdown"}


def test_parse_port_access_aruba_with_client():
    sample = """Client MAC      Auth Method  Status
00:11:22:33:44:55  dot1x       Authenticated
"""
    result = parse_port_access_aruba(sample)
    assert result == {"enabled": True, "status": "Authenticated"}


def test_parse_port_access_aruba_no_client():
    assert parse_port_access_aruba("No clients found") == {
        "enabled": False,
        "status": "No client",
    }


def test_parse_route_checkpoint_found():
    result = parse_route_checkpoint("via 10.0.0.1, eth0")
    assert result == {"nextHop": "10.0.0.1", "interface": "eth0"}


def test_parse_route_checkpoint_not_found():
    assert parse_route_checkpoint("no route to host") == {
        "nextHop": None,
        "interface": None,
    }


def test_ping_host_builds_command(monkeypatch):
    class FakeResult:
        stdout = "4 packets transmitted, 4 received, 0% packet loss, time 3005ms"

    def fake_run(cmd, **kwargs):
        assert cmd == ["ping", "-c", "4", "-W", "2", "10.0.0.1"]
        assert kwargs["capture_output"] is True
        return FakeResult()

    import troubleshoot_logic

    monkeypatch.setattr(troubleshoot_logic.subprocess, "run", fake_run)
    assert ping_host("10.0.0.1") == FakeResult.stdout
