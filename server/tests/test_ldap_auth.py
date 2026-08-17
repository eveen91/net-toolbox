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