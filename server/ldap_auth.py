"""
Active Directory authentication via direct bind. Deliberately does NOT
use a stored service account — the username/password the user typed
into the login form is used directly to bind to AD. This means no
long-lived directory credential is ever stored by this application.
"""
from typing import Dict, Optional

from ldap3 import Server, Connection, Tls, SUBTREE
import socket
import ssl


class AdAuthError(Exception):
    """Raised when AD authentication fails for a reportable reason."""


def authenticate_ad_user(
    username: str,
    password: str,
    host: str,
    port: int,
    use_tls: bool,
    domain_suffix: str,
) -> Optional[Dict]:
    if not password:
        # A blank password can bind anonymously against many LDAP
        # servers, which would "succeed" without authenticating
        # anyone. Reject this before ever touching the network.
        return None

    if not username:
        return None

    user_principal_name = f"{username}@{domain_suffix}" if "@" not in username else username
    tls_config = Tls(validate=ssl.CERT_REQUIRED) if use_tls else None
    server = Server(host, port=port, use_ssl=use_tls, tls=tls_config)

    try:
        conn = Connection(server, user=user_principal_name, password=password, auto_bind=True)
    except Exception:
        return None

    # Built from the server-configured domain_suffix rather than parsed out
    # of user_principal_name — the username the user typed is untrusted
    # input, and an inline split()/replace()/join() of it is both fragile
    # (see the hand-verified alternative dropped in favor of this) and, if
    # it were derived from user input, would let a typed-in "@domain" steer
    # which part of the directory we search rather than the admin's setting.
    dc_parts = domain_suffix.split(".")
    search_base = ",".join(f"DC={part}" for part in dc_parts)

    try:
        conn.search(
            search_base=search_base,
            search_filter=f"(userPrincipalName={user_principal_name})",
            search_scope=SUBTREE,
            attributes=["memberOf", "displayName"],
        )
    except Exception:
        member_of = []
    else:
        member_of = []
        if conn.entries:
            entry = conn.entries[0]
            if hasattr(entry, "memberOf"):
                member_of = [str(v) for v in entry.memberOf.values]

    conn.unbind()

    return {"username": username, "memberOf": member_of}


def is_member_of(member_of: list, group_dn: Optional[str]) -> bool:
    if not group_dn:
        return True  # no group restriction configured — allow
    return any(dn.lower() == group_dn.lower() for dn in member_of)


def resolve_role(member_of: list, admin_group_dn: Optional[str]) -> str:
    if admin_group_dn and is_member_of(member_of, admin_group_dn):
        return "admin"
    return "user"


def test_ad_connection(host: str, port: int, use_tls: bool, timeout: float = 5.0) -> Dict:
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
    except Exception as exc:
        return {"reachable": False, "tlsValid": None, "error": str(exc)}

    if not use_tls:
        sock.close()
        return {"reachable": True, "tlsValid": None, "error": None}

    try:
        context = ssl.create_default_context()
        wrapped = context.wrap_socket(sock, server_hostname=host)
        wrapped.close()
        return {"reachable": True, "tlsValid": True, "error": None}
    except ssl.SSLError as exc:
        try:
            sock.close()
        except Exception:
            pass
        return {"reachable": True, "tlsValid": False, "error": str(exc)}
    except Exception as exc:
        return {"reachable": True, "tlsValid": None, "error": str(exc)}