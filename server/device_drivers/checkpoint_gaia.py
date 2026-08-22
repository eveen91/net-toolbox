def get_version(session):
    return session.send_command("show version all")


def get_arp_table(session):
    return session.send_command("show arp dynamic all")


def get_route(session, ip):
    return session.send_command(f"show route to {ip}")
