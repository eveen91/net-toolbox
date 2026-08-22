import time


def get_version(session):
    return session.send_command("show version")


def get_mac_table(session):
    return session.send_command("show mac address-table")


def get_interface_status(session, port):
    return session.send_command(f"show interface {port}")


def get_interface_errors(session, port):
    return session.send_command(f"show interface {port} counters errors")


def run_cable_diagnostics(session, port):
    session.send_command(f"test cable-diagnostics tdr interface {port}")
    time.sleep(5)
    return session.send_command(f"show cable-diagnostics tdr interface {port}")


def get_transceiver_detail(session, port):
    return session.send_command(f"show interface {port} transceiver detail")


def get_spanning_tree_detail(session):
    return session.send_command("show spanning-tree detail")


def get_port_security(session, port):
    return session.send_command(f"show port-security interface {port}")
