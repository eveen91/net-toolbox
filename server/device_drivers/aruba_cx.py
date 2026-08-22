def get_version(session):
    return session.send_command("show version")


def get_mac_table(session):
    return session.send_command("show mac-address-table")


def get_interface_status(session, port):
    return session.send_command(f"show interface {port}")


def run_cable_diagnostics(session, port):
    return session.send_command(f"diag cable-diagnostic {port}")


def get_transceiver_detail(session, port):
    return session.send_command(f"show interface {port} transceiver detail")


def get_spanning_tree_detail(session):
    return session.send_command("show spanning-tree detail")


def get_port_access(session, port):
    return session.send_command(f"show port-access clients interface {port}")
