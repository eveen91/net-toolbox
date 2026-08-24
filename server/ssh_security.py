"""
Shared SSH host-key verification for the backend.

Centralizes the host-key policy so that every SSH client in the app —
the connection-test Linux sources (paramiko) and the device drivers
(netmiko) — verifies server host keys instead of auto-accepting unknown
hosts (which would let a man-in-the-middle capture credentials).

Host keys are loaded from the user's system known_hosts and a
project-level ``server/known_hosts`` file. Unknown hosts are rejected
(fail closed). To trust a new host, add its key on a machine you trust:

    ssh-keyscan -H <host> >> server/known_hosts

or add it to your ``~/.ssh/known_hosts``.
"""
from pathlib import Path

import paramiko

KNOWN_HOSTS_PATH = Path(__file__).parent / "known_hosts"


def configure_ssh_client(client: paramiko.SSHClient) -> None:
    """Load trusted host keys and reject anything unknown."""
    client.load_system_host_keys()
    if KNOWN_HOSTS_PATH.is_file():
        client.load_host_keys(str(KNOWN_HOSTS_PATH))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
