import ipaddress


def interface_network(interface):
    address = interface['ipAddress'].strip()
    if '/' not in address:
        raise ValueError('Interface has no subnet mask; a network cannot be inferred')
    parsed = ipaddress.ip_interface(address)
    if parsed.version != 4:
        raise ValueError('IPAM supports IPv4 networks only')
    return str(parsed.network)


def source_description(host, interfaces):
    first = interfaces[0]
    origin = f"Routing Map: {host} / {first['name']} ({first['ipAddress']})"
    description = (first.get('description') or '').strip()
    return (f'{origin} — {description}' if description else origin)[:500]
