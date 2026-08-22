import pytest
import ldap_auth
import auth_db


def _fresh_role(name="helpdesk", permissions=None):
    return auth_db.create_role(name, permissions or [])


def test_add_and_list_role_group(client):
    role = _fresh_role()
    auth_db.add_role_group(role["id"], "CN=Helpdesk,DC=test,DC=com")
    assert auth_db.list_role_groups(role["id"]) == ["CN=Helpdesk,DC=test,DC=com"]


def test_add_role_group_rejects_duplicate_dn_on_different_role(client):
    role_a = _fresh_role("helpdesk")
    role_b = _fresh_role("netops")
    auth_db.add_role_group(role_a["id"], "CN=Helpdesk,DC=test,DC=com")
    with pytest.raises(ValueError, match="helpdesk"):
        auth_db.add_role_group(role_b["id"], "CN=Helpdesk,DC=test,DC=com")


def test_add_role_group_rejects_missing_role(client):
    with pytest.raises(ValueError):
        auth_db.add_role_group(999999, "CN=Nowhere,DC=test,DC=com")


def test_remove_role_group(client):
    role = _fresh_role()
    auth_db.add_role_group(role["id"], "CN=Helpdesk,DC=test,DC=com")
    auth_db.remove_role_group(role["id"], "CN=Helpdesk,DC=test,DC=com")
    assert auth_db.list_role_groups(role["id"]) == []


def test_list_all_role_group_bindings(client):
    role_a = _fresh_role("helpdesk")
    role_b = _fresh_role("netops")
    auth_db.add_role_group(role_a["id"], "CN=Helpdesk,DC=test,DC=com")
    auth_db.add_role_group(role_b["id"], "CN=Netops,DC=test,DC=com")
    bindings = auth_db.list_all_role_group_bindings()
    names = sorted(b["roleName"] for b in bindings)
    assert names == ["helpdesk", "netops"]


def test_delete_role_blocked_while_ad_group_bound(client):
    role = _fresh_role()
    auth_db.add_role_group(role["id"], "CN=Helpdesk,DC=test,DC=com")
    with pytest.raises(ValueError, match="AD group"):
        auth_db.delete_role(role["id"])


def test_delete_role_succeeds_after_bindings_removed(client):
    role = _fresh_role()
    auth_db.add_role_group(role["id"], "CN=Helpdesk,DC=test,DC=com")
    auth_db.remove_role_group(role["id"], "CN=Helpdesk,DC=test,DC=com")
    auth_db.delete_role(role["id"])
    assert auth_db.get_role_by_id(role["id"]) is None


def test_resolve_role_from_bindings_single_match():
    bindings = [
        {"roleId": 1, "roleName": "helpdesk", "groupDn": "CN=Helpdesk,DC=test,DC=com"},
    ]
    role = ldap_auth.resolve_role_from_bindings(["CN=Helpdesk,DC=test,DC=com"], bindings)
    assert role == "helpdesk"


def test_resolve_role_from_bindings_no_match():
    bindings = [
        {"roleId": 1, "roleName": "helpdesk", "groupDn": "CN=Helpdesk,DC=test,DC=com"},
    ]
    assert ldap_auth.resolve_role_from_bindings([], bindings) is None
    assert ldap_auth.resolve_role_from_bindings(["CN=Nobody,DC=test,DC=com"], bindings) is None


def test_resolve_role_from_bindings_admin_wins_on_multiple_match():
    bindings = [
        {"roleId": 1, "roleName": "admin", "groupDn": "CN=Admins,DC=test,DC=com"},
        {"roleId": 2, "roleName": "helpdesk", "groupDn": "CN=Helpdesk,DC=test,DC=com"},
    ]
    role = ldap_auth.resolve_role_from_bindings(
        ["CN=Admins,DC=test,DC=com", "CN=Helpdesk,DC=test,DC=com"], bindings
    )
    assert role == "admin"


def test_ad_login_assigns_role_from_matched_binding(client, monkeypatch):
    role = auth_db.create_role("helpdesk", [])
    auth_db.add_role_group(role["id"], "CN=Helpdesk,DC=test,DC=com")

    auth_db.set_ad_setting("enabled", "true")
    auth_db.set_ad_setting("host", "ldap.example.com")
    auth_db.set_ad_setting("port", "636")
    auth_db.set_ad_setting("use_tls", "true")
    auth_db.set_ad_setting("domain_suffix", "example.com")

    def fake_authenticate(*args, **kwargs):
        return {
            "username": "opal",
            "memberOf": [],
            "isRequiredMember": True,
            "isAdminMember": False,
            "matchedGroupDns": ["CN=Helpdesk,DC=test,DC=com"],
        }

    monkeypatch.setattr(ldap_auth, "authenticate_ad_user", fake_authenticate)

    res = client.post(
        "/api/auth/login",
        json={"username": "opal", "password": "pw", "authMethod": "ad"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["role"] == "helpdesk"


def _login_as_admin(client):
    import auth
    auth_db.create_user("root", auth.hash_password("rootpass123"), role="admin")
    res = client.post(
        "/api/auth/login", json={"username": "root", "password": "rootpass123"}
    )
    assert res.status_code == 200, res.text


def test_api_add_and_remove_role_ad_group(client):
    _login_as_admin(client)
    role = auth_db.create_role("netops", [])

    res = client.get(f"/api/admin/roles/{role['id']}/ad-groups")
    assert res.status_code == 200
    assert res.json() == []

    res = client.post(
        f"/api/admin/roles/{role['id']}/ad-groups",
        json={"groupDn": "CN=Netops,DC=test,DC=com"},
    )
    assert res.status_code == 200, res.text
    assert res.json() == ["CN=Netops,DC=test,DC=com"]

    res = client.request(
        "DELETE",
        f"/api/admin/roles/{role['id']}/ad-groups",
        json={"groupDn": "CN=Netops,DC=test,DC=com"},
    )
    assert res.status_code == 200, res.text
    assert res.json() == []


def test_api_add_role_ad_group_conflict(client):
    _login_as_admin(client)
    role_a = auth_db.create_role("helpdesk", [])
    role_b = auth_db.create_role("netops", [])

    res = client.post(
        f"/api/admin/roles/{role_a['id']}/ad-groups",
        json={"groupDn": "CN=Shared,DC=test,DC=com"},
    )
    assert res.status_code == 200

    res = client.post(
        f"/api/admin/roles/{role_b['id']}/ad-groups",
        json={"groupDn": "CN=Shared,DC=test,DC=com"},
    )
    assert res.status_code == 400
    assert "helpdesk" in res.json()["detail"]


def test_role_list_includes_ad_groups(client):
    _login_as_admin(client)
    role = auth_db.create_role("helpdesk", [])
    auth_db.add_role_group(role["id"], "CN=Helpdesk,DC=test,DC=com")

    res = client.get("/api/admin/roles")
    assert res.status_code == 200
    match = next(r for r in res.json() if r["name"] == "helpdesk")
    assert match["adGroups"] == ["CN=Helpdesk,DC=test,DC=com"]


def test_role_change_blocked_for_ad_account(client):
    _login_as_admin(client)
    ad_user = auth_db.create_user("opal", "", role="user", auth_source="ad")

    res = client.patch(f"/api/admin/users/{ad_user['id']}/role", json={"role": "admin"})
    assert res.status_code == 400
    assert "Active Directory" in res.json()["detail"]


def test_role_change_still_works_for_local_account(client):
    _login_as_admin(client)
    local_user = auth_db.create_user("sam", "not-a-real-hash", role="user", auth_source="local")

    res = client.patch(f"/api/admin/users/{local_user['id']}/role", json={"role": "admin"})
    assert res.status_code == 200, res.text
    assert res.json()["role"] == "admin"