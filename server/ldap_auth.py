"""
Active Directory authentication via direct bind. Deliberately does NOT
use a stored service account — the username/password the user typed
into the login form is used directly to bind to AD. This means no
long-lived directory credential is ever stored by this application.
"""
from typing import Dict, Optional

from ldap3 import Server, Connection, Tls, SUBTREE
from ldap3.utils.conv import escape_filter_chars
import socket
import ssl

# AD's OID for transitive ("in chain") group membership — lets a single
# search resolve nested groups (e.g. an admin group that is itself a
# member of the base access group) the same way AD itself would, instead
# of only seeing the groups a user was added to directly.
LDAP_MATCHING_RULE_IN_CHAIN = "1.2.840.113556.1.4.1941"


class AdAuthError(Exception):
    """Raised when AD authentication fails for a reportable reason."""


def authenticate_ad_user(
    username: str,
    password: str,
    host: str,
    port: int,
    use_tls: bool,
    domain_suffix: str,
    required_group_dn: Optional[str] = None,
    admin_group_dn: Optional[str] = None,
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

    user_dn = None
    try:
        conn.search(
            search_base=search_base,
            search_filter=f"(userPrincipalName={escape_filter_chars(user_principal_name)})",
            search_scope=SUBTREE,
            attributes=["memberOf", "displayName"],
        )
    except Exception:
        member_of = []
    else:
        member_of = []
        if conn.entries:
            entry = conn.entries[0]
            user_dn = entry.entry_dn
            if hasattr(entry, "memberOf"):
                member_of = [str(v) for v in entry.memberOf.values]

    def _is_transitive_member(group_dn: str) -> bool:
        # Direct membership (already in member_of) covers the common case
        # cheaply; fall back to AD's transitive-membership matching rule
        # for groups nested inside other groups, so an account only added
        # to a nested admin group isn't rejected just because it was never
        # added to the outer group directly.
        if any(dn.lower() == group_dn.lower() for dn in member_of):
            return True
        if not user_dn:
            return False
        try:
            conn.search(
                search_base=search_base,
                search_filter=(
                    f"(&(distinguishedName={escape_filter_chars(user_dn)})"
                    f"(memberOf:{LDAP_MATCHING_RULE_IN_CHAIN}:={escape_filter_chars(group_dn)}))"
                ),
                search_scope=SUBTREE,
            )
        except Exception:
            return False
        return bool(conn.entries)

    is_admin_member = _is_transitive_member(admin_group_dn) if admin_group_dn else False
    # Admin-group membership always satisfies the required-group gate, even
    # if the admin group isn't nested inside (or duplicated into) the base
    # access group in AD — an admin shouldn't need to be added to two
    # separate groups just to be allowed to log in at all.
    is_required_member = (
        True
        if not required_group_dn
        else (is_admin_member or _is_transitive_member(required_group_dn))
    )

    conn.unbind()

    return {
        "username": username,
        "memberOf": member_of,
        "isRequiredMember": bool(is_required_member),
        "isAdminMember": bool(is_admin_member),
    }


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