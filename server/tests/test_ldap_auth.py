def test_authenticate_rejects_empty_password():
    import ldap_auth

    result = ldap_auth.authenticate_ad_user("someone", "", "ldap.example.com", 636, True, "example.com")
    assert result is None


def test_authenticate_rejects_empty_username():
    import ldap_auth

    result = ldap_auth.authenticate_ad_user("", "somepassword", "ldap.example.com", 636, True, "example.com")
    assert result is None


def test_authenticate_returns_none_on_bind_failure(monkeypatch):
    import ldap_auth

    class FakeConnectionThatFails:
        def __init__(self, *args, **kwargs):
            raise Exception("simulated bind failure")

    monkeypatch.setattr(ldap_auth, "Connection", FakeConnectionThatFails)
    result = ldap_auth.authenticate_ad_user("someone", "wrongpassword", "ldap.example.com", 636, True, "example.com")
    assert result is None


def test_is_member_of_with_no_group_configured_allows_anyone():
    import ldap_auth

    assert ldap_auth.is_member_of([], None) is True


def test_is_member_of_checks_membership_case_insensitively():
    import ldap_auth

    member_of = ["CN=Everyone,DC=example,DC=com"]
    assert ldap_auth.is_member_of(member_of, "cn=everyone,dc=example,dc=com") is True
    assert ldap_auth.is_member_of(member_of, "CN=Nobody,DC=example,DC=com") is False


def test_resolve_role_grants_admin_for_matching_group():
    import ldap_auth

    member_of = ["CN=IT-Admins,DC=example,DC=com"]
    assert ldap_auth.resolve_role(member_of, "CN=IT-Admins,DC=example,DC=com") == "admin"


def test_resolve_role_defaults_to_user():
    import ldap_auth

    assert ldap_auth.resolve_role([], None) == "user"


def test_authenticate_allows_member_of_role_bound_group_not_in_required_group(monkeypatch):
    """A user whose only AD group is bound to a custom role (e.g. via
    add_role_group) must be allowed to log in even when that group isn't
    the configured base "required" group and isn't nested inside it —
    a role binding is itself an explicit grant of access."""
    import ldap_auth

    helpdesk_dn = "CN=Helpdesk,DC=example,DC=com"
    required_dn = "CN=BaseAccess,DC=example,DC=com"

    class FakeEntry:
        entry_dn = "CN=opal,DC=example,DC=com"

        class memberOf:
            values = [helpdesk_dn]

    class FakeConnection:
        def __init__(self, *args, **kwargs):
            self.entries = [FakeEntry()]

        def search(self, search_base, search_filter, search_scope, attributes=None):
            # Only the direct userPrincipalName lookup returns the entry;
            # transitive-membership searches for groups the user isn't in
            # (directly or nested) return no entries.
            if "userPrincipalName" in search_filter:
                self.entries = [FakeEntry()]
            else:
                self.entries = []

        def unbind(self):
            pass

    monkeypatch.setattr(ldap_auth, "Connection", FakeConnection)

    result = ldap_auth.authenticate_ad_user(
        "opal",
        "somepassword",
        "ldap.example.com",
        636,
        True,
        "example.com",
        required_group_dn=required_dn,
        admin_group_dn="CN=Admins,DC=example,DC=com",
        candidate_group_dns=[helpdesk_dn],
    )

    assert result is not None
    assert result["isRequiredMember"] is True
    assert result["isAdminMember"] is False
    assert result["matchedGroupDns"] == [helpdesk_dn]