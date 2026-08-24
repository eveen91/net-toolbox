def get_version(session):
    return session.send_command("show version")


def get_mac_table(session):
    return session.send_command("show mac-address-table")


def get_interface_brief(session):
    return session.send_command("show interface brief")


def get_vsx_status(session):
    return session.send_command("show vsx status")


def get_bgp_summary(session):
    return session.send_command("show bgp all summary")


def get_ospf_neighbors(session):
    return session.send_command("show ip ospf neighbor")


def get_interface_errors(session):
    return session.send_command("show interface error-statistics")

