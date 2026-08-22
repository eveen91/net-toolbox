import re
import subprocess

from device_drivers.base import DeviceSession
from device_drivers import get_driver
import troubleshoot_devices


def parse_arp_table(raw_text):
    pairs = re.findall(
        r"(\d{1,3}(?:\.\d{1,3}){3}).*?([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})",
        raw_text,
    )
    return [{"ip": ip, "mac": mac.lower()} for ip, mac in pairs]


def parse_mac_table_cisco(raw_text):
    entries = []
    for line in raw_text.splitlines():
        m = re.match(
            r"\s*(\d+)\s+([0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})\s+\S+\s+(\S+)",
            line,
        )
        if m:
            vlan, dotted_mac, port = m.group(1), m.group(2), m.group(3)
            mac_colon = ":".join(
                dotted_mac.replace(".", "")[i : i + 2] for i in range(0, 12, 2)
            ).lower()
            entries.append({"vlan": vlan, "mac": mac_colon, "port": port})
    return entries


def parse_mac_table_aruba(raw_text):
    entries = []
    for line in raw_text.splitlines():
        m = re.match(
            r"\s*([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})\s+(\d+)\s+\S+\s+(\S+)",
            line,
        )
        if m:
            mac, vlan, port = m.group(1), m.group(2), m.group(3)
            entries.append({"mac": mac.lower(), "vlan": vlan, "port": port})
    return entries


def resolve_ip_to_mac(ip, gateway_device, username, password):
    with DeviceSession(
        gateway_device["deviceType"],
        gateway_device["mgmtIp"],
        username,
        password,
    ) as session:
        driver = get_driver(gateway_device["deviceType"])
        raw_text = driver.get_arp_table(session)
    entries = parse_arp_table(raw_text)
    for entry in entries:
        if entry["ip"] == ip:
            return entry["mac"]
    return None


def locate_mac_on_switches(mac, switch_devices, username, password):
    mac = mac.lower()
    for device in switch_devices:
        try:
            with DeviceSession(
                device["deviceType"],
                device["mgmtIp"],
                username,
                password,
            ) as session:
                driver = get_driver(device["deviceType"])
                raw_text = driver.get_mac_table(session)
                if device["deviceType"] == "cisco_ios":
                    entries = parse_mac_table_cisco(raw_text)
                elif device["deviceType"] == "aruba_aoscx":
                    entries = parse_mac_table_aruba(raw_text)
                else:
                    continue
                for entry in entries:
                    if entry["mac"] == mac:
                        return {
                            "device": device["name"],
                            "port": entry["port"],
                            "vlan": entry["vlan"],
                        }
        except Exception:
            continue
    return None


def parse_interface_status_cisco(raw_text):
    admin_match = re.search(
        r"is (up|administratively down|down),\s*line protocol is (up|down)", raw_text
    )
    adminStatus = "up" if admin_match and admin_match.group(1) == "up" else "down"
    operStatus = admin_match.group(2) if admin_match else "unknown"
    duplex_speed_match = re.search(r"(Full|Half)-duplex,\s*(\d+\w*b/s)", raw_text)
    duplex = duplex_speed_match.group(1) if duplex_speed_match else "unknown"
    speed = duplex_speed_match.group(2) if duplex_speed_match else "unknown"
    return {
        "adminStatus": adminStatus,
        "operStatus": operStatus,
        "duplex": duplex,
        "speed": speed,
    }


def parse_interface_errors_cisco(raw_text):
    for line in raw_text.splitlines():
        m = re.match(
            r"\s*\S+\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", line
        )
        if m:
            return {
                "alignErr": int(m.group(1)),
                "fcsErr": int(m.group(2)),
                "xmitErr": int(m.group(3)),
                "rcvErr": int(m.group(4)),
                "underSize": int(m.group(5)),
                "outDiscards": int(m.group(6)),
            }
    return {
        "alignErr": None,
        "fcsErr": None,
        "xmitErr": None,
        "rcvErr": None,
        "underSize": None,
        "outDiscards": None,
    }


def parse_interface_status_aruba(raw_text):
    admin_match = re.search(r"Admin state is (up|down)", raw_text)
    adminStatus = admin_match.group(1) if admin_match else "unknown"
    state_match = re.search(r"State information:\s*(up|down)", raw_text)
    operStatus = state_match.group(1) if state_match else "unknown"
    speed_match = re.search(r"Speed (\d+)", raw_text)
    speed = speed_match.group(1) + "Mb/s" if speed_match else "unknown"
    input_err_match = re.search(r"(\d+)\s+input errors", raw_text)
    inputErrors = int(input_err_match.group(1)) if input_err_match else None
    output_err_match = re.search(r"(\d+)\s+output errors", raw_text)
    outputErrors = int(output_err_match.group(1)) if output_err_match else None
    crc_match = re.search(r"(\d+)\s+CRC/FCS", raw_text)
    crcErrors = int(crc_match.group(1)) if crc_match else None
    return {
        "adminStatus": adminStatus,
        "operStatus": operStatus,
        "speed": speed,
        "duplex": "unknown",
        "inputErrors": inputErrors,
        "outputErrors": outputErrors,
        "crcErrors": crcErrors,
    }


def get_port_health(device, port, username, password):
    with DeviceSession(
        device["deviceType"], device["mgmtIp"], username, password
    ) as session:
        driver = get_driver(device["deviceType"])
        if device["deviceType"] == "cisco_ios":
            status_raw = driver.get_interface_status(session, port)
            errors_raw = driver.get_interface_errors(session, port)
            status = parse_interface_status_cisco(status_raw)
            errors = parse_interface_errors_cisco(errors_raw)
            return {
                "adminStatus": status["adminStatus"],
                "operStatus": status["operStatus"],
                "speed": status["speed"],
                "duplex": status["duplex"],
                "inputErrors": errors["rcvErr"],
                "outputErrors": errors["xmitErr"],
                "crcErrors": errors["fcsErr"],
            }
        elif device["deviceType"] == "aruba_aoscx":
            status_raw = driver.get_interface_status(session, port)
            status = parse_interface_status_aruba(status_raw)
            return {
                "adminStatus": status["adminStatus"],
                "operStatus": status["operStatus"],
                "speed": status["speed"],
                "duplex": status["duplex"],
                "inputErrors": status["inputErrors"],
                "outputErrors": status["outputErrors"],
                "crcErrors": status["crcErrors"],
            }
        else:
            raise ValueError(
                f"Port health not supported for device type {device['deviceType']}"
            )


def parse_cable_diagnostics_cisco(raw_text):
    matches = re.findall(
        r"Pair\s+([A-D])\s+(\d+)\s+\+/-.*?Pair\s+[A-D]\s+(\S+)", raw_text
    )
    return [
        {"pair": p, "lengthMeters": int(l), "status": s} for p, l, s in matches
    ]


def parse_cable_diagnostics_aruba(raw_text):
    entries = []
    for line in raw_text.splitlines():
        m = re.match(r"\s*([A-D])\s+(\S+)\s+(\d+)\s*m", line)
        if m:
            entries.append(
                {"pair": m.group(1), "status": m.group(2), "lengthMeters": int(m.group(3))}
            )
    return entries


def run_cable_test(device, port, username, password):
    with DeviceSession(
        device["deviceType"], device["mgmtIp"], username, password
    ) as session:
        driver = get_driver(device["deviceType"])
        raw_text = driver.run_cable_diagnostics(session, port)
        if device["deviceType"] == "cisco_ios":
            pairs = parse_cable_diagnostics_cisco(raw_text)
        elif device["deviceType"] == "aruba_aoscx":
            pairs = parse_cable_diagnostics_aruba(raw_text)
        else:
            raise ValueError(
                f"Cable diagnostics not supported for device type {device['deviceType']}"
            )
    return {"pairs": pairs}


def parse_transceiver_cisco(raw_text):
    metrics = {}
    specs = [
        ("Temperature", "C", "temperature"),
        ("Voltage", "V", "voltage"),
        ("Bias current", "mA", "biasCurrent"),
        ("Tx Power", "dBm", "txPower"),
        ("Rx Power", "dBm", "rxPower"),
    ]
    for name, unit, key in specs:
        pattern = (
            rf"{name}\s+(-?\d+\.?\d*)\s*{unit}\s+(-?\d+\.?\d*)\s*{unit}"
            rf"\s+(-?\d+\.?\d*)\s*{unit}\s+(-?\d+\.?\d*)\s*{unit}"
            rf"\s+(-?\d+\.?\d*)\s*{unit}"
        )
        m = re.search(pattern, raw_text)
        if m:
            metrics[key] = {
                "value": float(m.group(1)),
                "highAlarm": float(m.group(2)),
                "highWarn": float(m.group(3)),
                "lowWarn": float(m.group(4)),
                "lowAlarm": float(m.group(5)),
            }
        else:
            metrics[key] = None
    return metrics


def parse_transceiver_aruba(raw_text):
    metrics = {}
    specs = [
        ("Temperature", "C", "temperature"),
        ("Voltage", "V", "voltage"),
        ("Bias Current", "mA", "biasCurrent"),
        ("TX Power", "dBm", "txPower"),
        ("RX Power", "dBm", "rxPower"),
    ]
    for name, unit, key in specs:
        pattern = (
            rf"{name}\s*:\s*(-?\d+\.?\d*)\s*{unit}\s*\("
            rf"Warning Low (-?\d+\.?\d*), Warning High (-?\d+\.?\d*), "
            rf"Alarm Low (-?\d+\.?\d*), Alarm High (-?\d+\.?\d*)\)"
        )
        m = re.search(pattern, raw_text)
        if m:
            metrics[key] = {
                "value": float(m.group(1)),
                "lowWarn": float(m.group(2)),
                "highWarn": float(m.group(3)),
                "lowAlarm": float(m.group(4)),
                "highAlarm": float(m.group(5)),
            }
        else:
            metrics[key] = None
    return metrics


def evaluate_transceiver_health(metrics):
    result = {}
    for key in ("temperature", "voltage", "biasCurrent", "txPower", "rxPower"):
        entry = metrics.get(key)
        if entry is None:
            result[key] = {"value": None, "status": "unknown"}
            continue
        value = entry["value"]
        if value >= entry["highAlarm"] or value <= entry["lowAlarm"]:
            status = "alarm"
        elif value >= entry["highWarn"] or value <= entry["lowWarn"]:
            status = "warn"
        else:
            status = "ok"
        result[key] = {**entry, "status": status}
    return result


def get_transceiver_health(device, port, username, password):
    with DeviceSession(
        device["deviceType"], device["mgmtIp"], username, password
    ) as session:
        driver = get_driver(device["deviceType"])
        raw_text = driver.get_transceiver_detail(session, port)
        if device["deviceType"] == "cisco_ios":
            metrics = parse_transceiver_cisco(raw_text)
        elif device["deviceType"] == "aruba_aoscx":
            metrics = parse_transceiver_aruba(raw_text)
        else:
            raise ValueError(
                f"Transceiver health not supported for device type {device['deviceType']}"
            )
    return evaluate_transceiver_health(metrics)


def parse_stp_detail_cisco(raw_text):
    matches = re.findall(
        r"Number of topology changes (\d+) last change occurred ([\d:]+) ago\s*\n\s*from (\S+)",
        raw_text,
    )
    return [
        {"port": port, "topologyChanges": int(topologyChanges), "lastChangeAgo": lastChangeAgo}
        for topologyChanges, lastChangeAgo, port in matches
    ]


def parse_stp_detail_aruba(raw_text):
    matches = re.findall(
        r"Port (\S+) - Topology changes: (\d+), last change ([\d:]+) ago",
        raw_text,
    )
    return [
        {"port": port, "topologyChanges": int(topologyChanges), "lastChangeAgo": lastChangeAgo}
        for port, topologyChanges, lastChangeAgo in matches
    ]


def stp_ago_to_seconds(ago_str):
    try:
        parts = ago_str.split(":")
        if len(parts) == 3:
            hours, minutes, seconds = parts
            return int(hours) * 3600 + int(minutes) * 60 + int(seconds)
        if len(parts) == 2:
            minutes, seconds = parts
            return int(minutes) * 60 + int(seconds)
        return 999999
    except Exception:
        return 999999


def get_stp_report_for_device(device, username, password):
    with DeviceSession(
        device["deviceType"], device["mgmtIp"], username, password
    ) as session:
        driver = get_driver(device["deviceType"])
        raw_text = driver.get_spanning_tree_detail(session)
        if device["deviceType"] == "cisco_ios":
            entries = parse_stp_detail_cisco(raw_text)
        elif device["deviceType"] == "aruba_aoscx":
            entries = parse_stp_detail_aruba(raw_text)
        else:
            raise ValueError(
                f"STP report not supported for device type {device['deviceType']}"
            )
    for entry in entries:
        entry["device"] = device["name"]
        entry["lastChangeSeconds"] = stp_ago_to_seconds(entry["lastChangeAgo"])
    return entries


def get_stp_report_all(devices, username, password):
    all_entries = []
    for device in devices:
        if device["deviceType"] not in ("cisco_ios", "aruba_aoscx"):
            continue
        try:
            all_entries.extend(get_stp_report_for_device(device, username, password))
        except Exception:
            continue
    all_entries.sort(key=lambda e: (-e["topologyChanges"], e["lastChangeSeconds"]))
    return all_entries


def parse_port_security_cisco(raw_text):
    enabled_match = re.search(r"Port Security\s*:\s*(\S+)", raw_text)
    status_match = re.search(r"Port Status\s*:\s*(\S+)", raw_text)
    enabled_str = enabled_match.group(1) if enabled_match else None
    status_str = status_match.group(1) if status_match else None
    return {
        "enabled": enabled_str.lower() == "enabled" if enabled_str else None,
        "status": status_str if status_str else None,
    }


def parse_port_access_aruba(raw_text):
    found = None
    for line in raw_text.splitlines():
        m = re.match(
            r"([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})\s+(dot1x|mac-auth|\S+)\s+(\w+)\s*$",
            line,
        )
        if m:
            found = m
            break
    if found:
        return {"enabled": True, "status": found.group(3)}
    return {"enabled": False, "status": "No client"}


def get_port_access_status(device, port, username, password):
    with DeviceSession(
        device["deviceType"], device["mgmtIp"], username, password
    ) as session:
        driver = get_driver(device["deviceType"])
        if device["deviceType"] == "cisco_ios":
            raw_text = driver.get_port_security(session, port)
            return parse_port_security_cisco(raw_text)
        elif device["deviceType"] == "aruba_aoscx":
            raw_text = driver.get_port_access(session, port)
            return parse_port_access_aruba(raw_text)
        else:
            raise ValueError(
                f"Access status not supported for device type {device['deviceType']}"
            )


def ping_host(ip):
    result = subprocess.run(
        ["ping", "-c", "4", "-W", "2", ip],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result.stdout


def parse_ping_output(raw_text):
    summary = re.search(
        r"(\d+) packets transmitted, (\d+) received,\s*([\d.]+)% packet loss", raw_text
    )
    rtt = re.search(r"rtt min/avg/max/mdev = [\d.]+/([\d.]+)/", raw_text)
    return {
        "packetsSent": int(summary.group(1)) if summary else None,
        "packetsReceived": int(summary.group(2)) if summary else None,
        "packetLossPercent": float(summary.group(3)) if summary else None,
        "avgLatencyMs": float(rtt.group(1)) if rtt else None,
    }


def parse_route_checkpoint(raw_text):
    m = re.search(r"via\s+(\d{1,3}(?:\.\d{1,3}){3}),?\s*(\S+)", raw_text)
    if m:
        return {"nextHop": m.group(1), "interface": m.group(2)}
    return {"nextHop": None, "interface": None}


def get_route_check(ip, gateway_device, username, password):
    with DeviceSession(
        gateway_device["deviceType"],
        gateway_device["mgmtIp"],
        username,
        password,
    ) as session:
        driver = get_driver(gateway_device["deviceType"])
        raw_text = driver.get_route(session, ip)
    return parse_route_checkpoint(raw_text)


def run_full_diagnostic(ip, username, password):
    result = {
        "ip": ip,
        "locate": None,
        "portHealth": None,
        "transceiverHealth": None,
        "accessStatus": None,
        "ping": None,
        "route": None,
    }
    devices = troubleshoot_devices.list_devices()
    gateway = next(
        (d for d in devices if d["deviceType"] == "checkpoint_gaia"), None
    )
    switches = [
        d for d in devices if d["deviceType"] in ("cisco_ios", "aruba_aoscx")
    ]

    try:
        raw = ping_host(ip)
        result["ping"] = {"success": True, **parse_ping_output(raw)}
    except Exception as e:
        result["ping"] = {"success": False, "error": str(e)}

    if gateway:
        try:
            route = get_route_check(ip, gateway, username, password)
            result["route"] = {"success": True, **route}
        except Exception as e:
            result["route"] = {"success": False, "error": str(e)}
    else:
        result["route"] = {"success": False, "error": "No gateway device configured"}

    if not gateway:
        result["locate"] = {"success": False, "error": "No gateway device configured"}
        return result

    try:
        mac = resolve_ip_to_mac(ip, gateway, username, password)
        if mac is None:
            result["locate"] = {"success": False, "error": "IP not found in ARP table"}
            return result
        located = locate_mac_on_switches(mac, switches, username, password)
        if located is None:
            result["locate"] = {
                "success": False,
                "error": f"MAC {mac} not found on any switch",
            }
            return result
        result["locate"] = {"success": True, "mac": mac, **located}
    except Exception as e:
        result["locate"] = {"success": False, "error": str(e)}
        return result

    device = next((d for d in devices if d["name"] == located["device"]), None)
    port = located["port"]
    if device is None:
        return result

    try:
        health = get_port_health(device, port, username, password)
        result["portHealth"] = {"success": True, **health}
    except Exception as e:
        result["portHealth"] = {"success": False, "error": str(e)}

    try:
        transceiver = get_transceiver_health(device, port, username, password)
        result["transceiverHealth"] = {"success": True, **transceiver}
    except Exception as e:
        result["transceiverHealth"] = {"success": False, "error": str(e)}

    try:
        access = get_port_access_status(device, port, username, password)
        result["accessStatus"] = {"success": True, **access}
    except Exception as e:
        result["accessStatus"] = {"success": False, "error": str(e)}

    return result
