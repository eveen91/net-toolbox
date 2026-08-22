"""
Active Directory authentication via direct bind. Deliberately does NOT
use a stored service account — the username/password the user typed
into the login form is used directly to bind to AD. This means no
long-lived directory credential is ever stored by this application.
"""
from typing import Dict, List, Optional

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
    candidate_group_dns: Optional[List[str]] = None,
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

    # Every AD-group-to-role binding the user transitively belongs to. Used
    # by the caller (main.py) to work out which role a first-time AD login
    # should be provisioned with — see resolve_role_from_bindings() below.
    matched_group_dns = [
        dn for dn in (candidate_group_dns or []) if _is_transitive_member(dn)
    ]

    # Admin-group membership, or membership in ANY role-bound AD group,
    # always satisfies the required-group gate — even if that group isn't
    # nested inside (or duplicated into) the base access group in AD. A
    # role binding is itself an explicit grant of access; a user shouldn't
    # need to also be added to a separate "base access" group just to be
    # allowed to log in once their group has been bound to a role.
    is_required_member = (
        True
        if not required_group_dn
        else (
            is_admin_member
            or bool(matched_group_dns)
            or _is_transitive_member(required_group_dn)
        )
    )

    conn.unbind()

    return {
        "username": username,
        "memberOf": member_of,
        "isRequiredMember": bool(is_required_member),
        "isAdminMember": bool(is_admin_member),
        "matchedGroupDns": matched_group_dns,
    }


def is_member_of(member_of: list, group_dn: Optional[str]) -> bool:
    if not group_dn:
        return True  # no group restriction configured — allow
    return any(dn.lower() == group_dn.lower() for dn in member_of)


def resolve_role(member_of: list, admin_group_dn: Optional[str]) -> str:
    if admin_group_dn and is_member_of(member_of, admin_group_dn):
        return "admin"
    return "user"


def resolve_role_from_bindings(matched_group_dns: List[str], bindings: List[Dict]) -> Optional[str]:
    """
    Given the DNs a user transitively belongs to (matched_group_dns, from
    authenticate_ad_user's "matchedGroupDns") and the full list of role<->AD
    group bindings (bindings, as returned by
    auth_db.list_all_role_group_bindings() — a list of
    {"roleId", "roleName", "groupDn"} dicts), return the name of the role
    that should be assigned, or None if nothing matched.

    A group DN can only ever be bound to one role (enforced when the
    binding is created), so this is only ambiguous when a user belongs to
    two DIFFERENT groups that are bound to two different roles. In that
    case: "admin" wins if it's one of the matches; otherwise the
    alphabetically-first matching role name wins, so the result is always
    deterministic.
    """
    matched_lower = {dn.lower() for dn in matched_group_dns}
    matched_role_names = {
        b["roleName"] for b in bindings if b["groupDn"].lower() in matched_lower
    }
    if not matched_role_names:
        return None
    if "admin" in matched_role_names:
        return "admin"
    return sorted(matched_role_names)[0]


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