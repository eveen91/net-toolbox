def get_version(session):
    return session.send_command("show version all")


def get_arp_table(session):
    return session.send_command("show arp dynamic all")


def get_route(session, ip):
    return session.send_command(f"show route to {ip}")


def get_ha_stat(session):
    return session.send_command("cphaprob stat")


def get_sync_stat(session):
    return session.send_command("cphaprob syncstat")


def get_policy_stat(session):
    return session.send_command("fw stat")

