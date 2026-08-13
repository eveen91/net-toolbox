"""
Helpers for scanning IPAM subnets.
"""

import ipaddress

MAX_SCAN_ADDRESSES = 1024


def enumerate_scan_targets(cidr: str, excludes: set[str]) -> list[str]:
    network = ipaddress.ip_network(cidr, strict=False)
    # network.hosts() already excludes the network address for both IPv4
    # and IPv6, and additionally excludes the broadcast address for IPv4.
    targets = sorted(
        str(addr) for addr in network.hosts() if str(addr) not in excludes
    )
    if len(targets) > MAX_SCAN_ADDRESSES:
        raise ValueError(
            f"{len(targets)} addresses to scan exceeds the maximum of {MAX_SCAN_ADDRESSES}"
        )
    return targets