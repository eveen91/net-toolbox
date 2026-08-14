"""
IPAM subnet autodiscovery.

Given a subnet's CIDR and a set of addresses to skip (scan excludes, plus
any reserved/locked addresses the caller filters out beforehand),
enumerate the host addresses worth probing, ping each one, and — for the
ones that answer — try a reverse-DNS lookup for a hostname.

scan_one() is the unit of work handed to a thread-pool executor by
main.py's /autodiscover endpoint, one call per target address. It calls
ping_host()/reverse_dns() as bare module-level names (not via self/import
aliasing) so that tests can patch.object(ipam_scan, "ping_host", ...) and
have scan_one() pick up the patched version.
"""

import ipaddress
import socket
import subprocess
from typing import Dict, List, Optional, Set

# Hard cap on how many addresses a single autodiscover run will enumerate —
# scanning something like a /16 would fan out to tens of thousands of pings
# per request, so subnets bigger than this are rejected outright rather than
# silently taking forever (or exhausting the executor's thread pool).
MAX_SCAN_ADDRESSES = 1024

DEFAULT_PING_TIMEOUT = 1.0  # seconds, per ping attempt
DEFAULT_PING_ATTEMPTS = 2
DEFAULT_DNS_TIMEOUT = 1.0  # seconds


def enumerate_scan_targets(cidr: str, excludes: Set[str]) -> List[str]:
    """
    Return the host addresses in `cidr` worth pinging: every usable host
    address (network/broadcast addresses excluded automatically by
    ip_network.hosts()) minus anything in `excludes`.

    Raises ValueError if the subnet is larger than MAX_SCAN_ADDRESSES.
    """
    network = ipaddress.ip_network(cidr, strict=False)
    if network.num_addresses > MAX_SCAN_ADDRESSES:
        raise ValueError(
            f"Subnet {cidr} has {network.num_addresses} addresses, which exceeds the "
            f"autodiscovery scan cap of {MAX_SCAN_ADDRESSES}. Break it into smaller "
            f"subnets to scan it."
        )
    return [str(addr) for addr in network.hosts() if str(addr) not in excludes]


def ping_host(address: str, timeout: float = DEFAULT_PING_TIMEOUT, attempts: int = DEFAULT_PING_ATTEMPTS) -> bool:
    """
    Best-effort liveness check via the system `ping` command. Tries up to
    `attempts` times (a single dropped probe shouldn't mark a live host as
    free), succeeding as soon as one attempt gets a reply.
    """
    for _ in range(max(1, attempts)):
        try:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", str(max(1, int(timeout))), address],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout + 1,
            )
            if result.returncode == 0:
                return True
        except (subprocess.SubprocessError, OSError):
            continue
    return False


def reverse_dns(address: str, timeout: float = DEFAULT_DNS_TIMEOUT) -> Optional[str]:
    """Best-effort reverse DNS lookup. Returns None on any failure or timeout."""
    old_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(timeout)
        return socket.gethostbyaddr(address)[0]
    except (socket.herror, socket.gaierror, socket.timeout, OSError):
        return None
    finally:
        socket.setdefaulttimeout(old_timeout)


def scan_one(
    address: str,
    ping_timeout: float = DEFAULT_PING_TIMEOUT,
    ping_attempts: int = DEFAULT_PING_ATTEMPTS,
    dns_timeout: float = DEFAULT_DNS_TIMEOUT,
) -> Dict:
    """Probe a single address: ping it, and if it answers, try to resolve a hostname."""
    alive = ping_host(address, ping_timeout, ping_attempts)
    hostname = reverse_dns(address, dns_timeout) if alive else None
    return {"address": address, "alive": alive, "hostname": hostname}