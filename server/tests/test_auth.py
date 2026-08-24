import auth


def test_hash_password_and_verify_correct_password():
    hashed = auth.hash_password("correct-horse-battery-staple")
    assert auth.verify_password("correct-horse-battery-staple", hashed) is True


def test_verify_wrong_password_fails():
    hashed = auth.hash_password("correct-horse-battery-staple")
    assert auth.verify_password("wrong-password", hashed) is False


def test_hash_password_is_not_plaintext():
    hashed = auth.hash_password("correct-horse-battery-staple")
    assert hashed != "correct-horse-battery-staple"


def test_generate_session_token_is_unique():
    a = auth.generate_session_token()
    b = auth.generate_session_token()
    assert a != b


def test_hash_token_is_deterministic():
    token = auth.generate_session_token()
    assert auth.hash_token(token) == auth.hash_token(token)


def test_session_info_shows_login_not_required_by_default(client):
    res = client.get("/api/auth/session")
    assert res.status_code == 200
    assert res.json()["loginRequired"] is False
    assert res.json()["user"] is None


def test_login_with_wrong_credentials_fails(client):
    res = client.post("/api/auth/login", json={"username": "nobody", "password": "wrong"})
    assert res.status_code == 401


def test_login_with_correct_credentials_succeeds(client):
    import auth_db, auth
    auth_db.create_user("alice", auth.hash_password("hunter2"), role="admin")
    res = client.post("/api/auth/login", json={"username": "alice", "password": "hunter2"})
    assert res.status_code == 200
    assert res.json()["username"] == "alice"
    assert "session_token" in res.cookies


def test_session_info_reflects_logged_in_user(client):
    import auth_db, auth
    auth_db.create_user("bob", auth.hash_password("hunter2"), role="user")
    client.post("/api/auth/login", json={"username": "bob", "password": "hunter2"})
    res = client.get("/api/auth/session")
    assert res.json()["user"]["username"] == "bob"


def test_logout_clears_session(client):
    import auth_db, auth
    auth_db.create_user("carol", auth.hash_password("hunter2"), role="user")
    client.post("/api/auth/login", json={"username": "carol", "password": "hunter2"})
    client.post("/api/auth/logout")
    res = client.get("/api/auth/session")
    assert res.json()["user"] is None


def test_protected_endpoint_open_when_login_not_required(client):
    res = client.get("/api/ipam/subnets")
    assert res.status_code != 401


def test_protected_endpoint_blocked_when_login_required_and_not_logged_in(client):
    import auth_db
    auth_db.set_setting("require_login", "true")
    res = client.get("/api/ipam/subnets")
    assert res.status_code == 401
    auth_db.set_setting("require_login", "false")


def test_list_users_open_when_login_not_required(client):
    import auth_db, auth
    auth_db.create_user("dave", auth.hash_password("pw"), role="user")
    res = client.get("/api/admin/users")
    assert res.status_code == 200
    assert "dave" in [u["username"] for u in res.json()]


def test_create_user_via_admin_endpoint(client):
    res = client.post("/api/admin/users", json={"username": "erin", "password": "Password123", "role": "user"})
    assert res.status_code == 200
    assert res.json()["username"] == "erin"
    assert "passwordHash" not in res.json()
    assert "password" not in res.json()


def test_create_user_rejects_duplicate_username(client):
    client.post("/api/admin/users", json={"username": "frank", "password": "Password1"})
    res = client.post("/api/admin/users", json={"username": "frank", "password": "Password2"})
    assert res.status_code == 400


def test_delete_user(client):
    created = client.post("/api/admin/users", json={"username": "gina", "password": "Password1"}).json()
    res = client.delete(f"/api/admin/users/{created['id']}")
    assert res.status_code == 200
    remaining = [u["username"] for u in client.get("/api/admin/users").json()]
    assert "gina" not in remaining


def test_cannot_delete_last_admin(client):
    import auth_db
    for u in auth_db.list_users():
        if u["role"] == "admin":
            auth_db.delete_user(u["id"])
    admin = client.post("/api/admin/users", json={"username": "only-admin", "password": "Password1", "role": "admin"}).json()
    # require_admin_user now requires a real admin session for any call
    # once an admin exists (it only bypasses auth in the count==0
    # bootstrap window), so we have to actually log in to reach the
    # handler at all.
    client.post("/api/auth/login", json={"username": "only-admin", "password": "Password1"})
    res = client.delete(f"/api/admin/users/{admin['id']}")
    assert res.status_code == 400


def test_reset_password_lets_user_log_in_with_new_password(client):
    created = client.post("/api/admin/users", json={"username": "helen", "password": "Password1"}).json()
    client.post(f"/api/admin/users/{created['id']}/reset-password", json={"newPassword": "Password2"})
    res = client.post("/api/auth/login", json={"username": "helen", "password": "Password2"})
    assert res.status_code == 200


def test_cannot_enable_login_without_being_logged_in_as_admin(client):
    import auth_db, auth
    auth_db.set_setting("require_login", "false")
    # set_require_login 400s outright when no admin exists at all, so an
    # admin has to exist for this request to reach the "must be logged in
    # as that admin" check it's actually testing. Deliberately not logging
    # in as them — that's the case under test.
    auth_db.create_user("ursula", auth.hash_password("Password1"), role="admin")
    res = client.post("/api/admin/settings/require-login", json={"enabled": True})
    assert res.status_code == 403
    assert auth_db.is_login_required() is False


def test_can_enable_login_when_logged_in_as_admin(client):
    import auth_db, auth
    auth_db.set_setting("require_login", "false")
    auth_db.create_user("ivan", auth.hash_password("Password1"), role="admin")
    client.post("/api/auth/login", json={"username": "ivan", "password": "Password1"})
    res = client.post("/api/admin/settings/require-login", json={"enabled": True})
    assert res.status_code == 200
    assert auth_db.is_login_required() is True
    auth_db.set_setting("require_login", "false")


def test_non_admin_cannot_disable_login_once_enabled(client):
    import auth_db, auth
    auth_db.set_setting("require_login", "false")
    # Same precondition as above: at least one admin must exist for the
    # request to get past set_require_login's "no admins yet" 400 and
    # actually reach the role check this test is exercising.
    auth_db.create_user("victor", auth.hash_password("admin-pw"), role="admin")
    auth_db.create_user("judy", auth.hash_password("pw"), role="user")
    client.post("/api/auth/login", json={"username": "judy", "password": "pw"})
    auth_db.set_setting("require_login", "true")
    res = client.post("/api/admin/settings/require-login", json={"enabled": False})
    assert res.status_code == 403
    auth_db.set_setting("require_login", "false")


def test_change_password_requires_login(client):
    res = client.post("/api/auth/change-password", json={"currentPassword": "a", "newPassword": "b"})
    assert res.status_code == 401


def test_change_password_rejects_wrong_current_password(client):
    import auth_db, auth
    auth_db.create_user("kevin", auth.hash_password("Password1"), role="user")
    client.post("/api/auth/login", json={"username": "kevin", "password": "Password1"})
    res = client.post("/api/auth/change-password", json={"currentPassword": "wrong-pw", "newPassword": "Password2"})
    assert res.status_code == 400


def test_change_password_succeeds_and_new_password_works(client):
    import auth_db, auth
    auth_db.create_user("laura", auth.hash_password("Password1"), role="user")
    client.post("/api/auth/login", json={"username": "laura", "password": "Password1"})
    res = client.post("/api/auth/change-password", json={"currentPassword": "Password1", "newPassword": "Password2"})
    assert res.status_code == 200
    client.post("/api/auth/logout")
    login_res = client.post("/api/auth/login", json={"username": "laura", "password": "Password2"})
    assert login_res.status_code == 200


def test_expired_session_is_rejected(client):
    import auth_db, auth
    from datetime import datetime, timezone, timedelta

    user = auth_db.create_user("mallory", auth.hash_password("pw"), role="user")
    token = auth.generate_session_token()
    auth_db.create_session(user["id"], token)

    # Manually push this session's expiry into the past, simulating an
    # old session — create_session always sets a future expiry, so we
    # go around it here directly against the auth database.
    conn = auth_db.get_connection()
    try:
        token_hash = auth.hash_token(token)
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        conn.execute("UPDATE sessions SET expires_at = ? WHERE token_hash = ?", (past, token_hash))
        conn.commit()
    finally:
        conn.close()

    result = auth_db.get_user_by_session_token(token)
    assert result is None


def test_login_endpoint_reachable_even_when_login_required_and_logged_out(client):
    import auth_db, auth
    auth_db.create_user("nate", auth.hash_password("pw"), role="user")
    auth_db.set_setting("require_login", "true")
    res = client.post("/api/auth/login", json={"username": "nate", "password": "pw"})
    assert res.status_code == 200
    auth_db.set_setting("require_login", "false")  # reset for later tests


def test_ad_login_fails_when_ad_not_enabled(client):
    res = client.post("/api/auth/login", json={"username": "someone", "password": "pw", "authMethod": "ad"})
    assert res.status_code == 401


def test_ad_login_succeeds_and_provisions_user(client, monkeypatch):
    import auth_db, ldap_auth
    auth_db.set_ad_setting("enabled", "true")
    auth_db.set_ad_setting("host", "ldap.example.com")
    auth_db.set_ad_setting("port", "636")
    auth_db.set_ad_setting("use_tls", "true")
    auth_db.set_ad_setting("domain_suffix", "example.com")

    monkeypatch.setattr(
        ldap_auth, "authenticate_ad_user",
        lambda *args, **kwargs: {
            "username": "opal", "memberOf": [],
            "isRequiredMember": True, "isAdminMember": False,
        }
    )

    res = client.post("/api/auth/login", json={"username": "opal", "password": "pw", "authMethod": "ad"})
    assert res.status_code == 200
    assert res.json()["username"] == "opal"

    user = auth_db.get_user_by_username("opal")
    assert user["authSource"] == "ad"

    auth_db.set_ad_setting("enabled", "false")


def test_ad_login_rejected_when_not_in_required_group(client, monkeypatch):
    import auth_db, ldap_auth
    auth_db.set_ad_setting("enabled", "true")
    auth_db.set_ad_setting("required_group_dn", "CN=VPN-Users,DC=example,DC=com")

    monkeypatch.setattr(
        ldap_auth, "authenticate_ad_user",
        lambda *args, **kwargs: {
            "username": "penny", "memberOf": ["CN=Everyone,DC=example,DC=com"],
            "isRequiredMember": False, "isAdminMember": False,
        }
    )

    res = client.post("/api/auth/login", json={"username": "penny", "password": "pw", "authMethod": "ad"})
    assert res.status_code == 401

    auth_db.set_ad_setting("enabled", "false")
    auth_db.set_ad_setting("required_group_dn", "")


def test_ad_login_coexists_with_existing_local_account_of_same_username(client, monkeypatch):
    # Superseded the old "does not take over" 401 expectation: since local
    # and AD usernames are now independent namespaces (Step 21), an AD
    # login no longer collides with a same-named local account at all — it
    # just provisions/reuses its own AD-sourced row alongside it.
    import auth_db, auth, ldap_auth
    auth_db.create_user("quinn", auth.hash_password("local-pw"), role="user", auth_source="local")
    auth_db.set_ad_setting("enabled", "true")

    monkeypatch.setattr(
        ldap_auth, "authenticate_ad_user",
        lambda *args, **kwargs: {
            "username": "quinn", "memberOf": [],
            "isRequiredMember": True, "isAdminMember": False,
        }
    )

    res = client.post("/api/auth/login", json={"username": "quinn", "password": "whatever", "authMethod": "ad"})
    assert res.status_code == 200
    assert res.json()["authSource"] == "ad"

    auth_db.set_ad_setting("enabled", "false")


def test_local_login_still_works_after_ad_changes(client):
    import auth_db, auth
    auth_db.create_user("rex", auth.hash_password("pw"), role="user")
    res = client.post("/api/auth/login", json={"username": "rex", "password": "pw", "authMethod": "local"})
    assert res.status_code == 200


def test_get_ad_settings_defaults(client):
    res = client.get("/api/admin/settings/ad")
    assert res.status_code == 200
    assert res.json()["enabled"] is False


def test_update_ad_settings_persists(client):
    payload = {
        "enabled": True,
        "host": "ldap.example.com",
        "port": 636,
        "useTls": True,
        "domainSuffix": "example.com",
        "requiredGroupDn": "CN=VPN-Users,DC=example,DC=com",
        "adminGroupDn": None,
    }
    res = client.put("/api/admin/settings/ad", json=payload)
    assert res.status_code == 200
    assert res.json()["host"] == "ldap.example.com"

    res2 = client.get("/api/admin/settings/ad")
    assert res2.json()["enabled"] is True
    assert res2.json()["requiredGroupDn"] == "CN=VPN-Users,DC=example,DC=com"

    # reset so later tests aren't affected
    client.put("/api/admin/settings/ad", json={**payload, "enabled": False})


def test_update_ad_settings_rejects_enabling_without_host(client):
    res = client.put("/api/admin/settings/ad", json={
        "enabled": True, "host": "", "port": 636, "useTls": True, "domainSuffix": "example.com",
    })
    assert res.status_code == 400


def test_update_ad_settings_rejects_invalid_port(client):
    res = client.put("/api/admin/settings/ad", json={
        "enabled": False, "host": "ldap.example.com", "port": 99999, "useTls": True, "domainSuffix": "example.com",
    })
    assert res.status_code == 400


def test_connection_test_reports_reachable(client, monkeypatch):
    import ldap_auth
    monkeypatch.setattr(
        ldap_auth, "test_ad_connection",
        lambda host, port, use_tls, timeout=5.0: {"reachable": True, "tlsValid": True, "error": None}
    )
    res = client.post("/api/admin/settings/ad/test-connection", json={
        "host": "ldap.example.com", "port": 636, "useTls": True,
    })
    assert res.status_code == 200
    assert res.json()["reachable"] is True
    assert res.json()["tlsValid"] is True


def test_connection_test_reports_unreachable(client, monkeypatch):
    import ldap_auth
    monkeypatch.setattr(
        ldap_auth, "test_ad_connection",
        lambda host, port, use_tls, timeout=5.0: {"reachable": False, "tlsValid": None, "error": "timed out"}
    )
    res = client.post("/api/admin/settings/ad/test-connection", json={
        "host": "unreachable.example.com", "port": 636, "useTls": True,
    })
    assert res.status_code == 200
    assert res.json()["reachable"] is False
    assert res.json()["error"] == "timed out"


def test_connection_test_falls_back_to_saved_config(client, monkeypatch):
    import auth_db, ldap_auth
    auth_db.set_ad_setting("host", "saved-host.example.com")
    auth_db.set_ad_setting("port", "389")
    auth_db.set_ad_setting("use_tls", "false")

    captured = {}

    def fake_test(host, port, use_tls, timeout=5.0):
        captured["host"] = host
        captured["port"] = port
        captured["use_tls"] = use_tls
        return {"reachable": True, "tlsValid": None, "error": None}

    monkeypatch.setattr(ldap_auth, "test_ad_connection", fake_test)

    res = client.post("/api/admin/settings/ad/test-connection", json={})
    assert res.status_code == 200
    assert captured["host"] == "saved-host.example.com"
    assert captured["port"] == 389
    assert captured["use_tls"] is False


def test_connection_test_requires_a_host(client, monkeypatch):
    import auth_db
    auth_db.set_ad_setting("host", "")
    res = client.post("/api/admin/settings/ad/test-connection", json={})
    assert res.status_code == 400


def test_local_and_ad_accounts_can_share_a_username(client, monkeypatch):
    import auth_db, auth, ldap_auth
    auth_db.create_user("sam", auth.hash_password("local-pw"), role="user", auth_source="local")
    auth_db.set_ad_setting("enabled", "true")
    monkeypatch.setattr(
        ldap_auth, "authenticate_ad_user",
        lambda *args, **kwargs: {
            "username": "sam", "memberOf": [],
            "isRequiredMember": True, "isAdminMember": False,
        }
    )

    res = client.post("/api/auth/login", json={"username": "sam", "password": "whatever", "authMethod": "ad"})
    assert res.status_code == 200
    assert res.json()["authSource"] == "ad"

    local_user = auth_db.get_user_by_username_and_source("sam", "local")
    ad_user = auth_db.get_user_by_username_and_source("sam", "ad")
    assert local_user is not None
    assert ad_user is not None
    assert local_user["id"] != ad_user["id"]

    auth_db.set_ad_setting("enabled", "false")


def test_local_login_matches_local_account_when_ad_duplicate_exists(client, monkeypatch):
    import auth_db, auth, ldap_auth
    auth_db.create_user("tara", auth.hash_password("local-pw"), role="user", auth_source="local")
    auth_db.set_ad_setting("enabled", "true")
    monkeypatch.setattr(
        ldap_auth, "authenticate_ad_user",
        lambda *args, **kwargs: {
            "username": "tara", "memberOf": [],
            "isRequiredMember": True, "isAdminMember": False,
        }
    )
    client.post("/api/auth/login", json={"username": "tara", "password": "whatever", "authMethod": "ad"})

    res = client.post("/api/auth/login", json={"username": "tara", "password": "local-pw", "authMethod": "local"})
    assert res.status_code == 200
    assert res.json()["authSource"] == "local"

    auth_db.set_ad_setting("enabled", "false")


def test_ad_relogin_reuses_existing_ad_account_not_a_new_one(client, monkeypatch):
    import auth_db, ldap_auth
    auth_db.set_ad_setting("enabled", "true")
    monkeypatch.setattr(
        ldap_auth, "authenticate_ad_user",
        lambda *args, **kwargs: {
            "username": "uma", "memberOf": [],
            "isRequiredMember": True, "isAdminMember": False,
        }
    )

    first = client.post("/api/auth/login", json={"username": "uma", "password": "pw", "authMethod": "ad"}).json()
    second = client.post("/api/auth/login", json={"username": "uma", "password": "pw", "authMethod": "ad"}).json()
    assert first["id"] == second["id"]

    auth_db.set_ad_setting("enabled", "false")


def test_migration_preserves_existing_users_and_relaxes_constraint(tmp_path, monkeypatch):
    import sqlite3
    import auth_db

    old_db_path = tmp_path / "old_style_auth.db"
    conn = sqlite3.connect(old_db_path)
    conn.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
        ("existing-user", "some-hash", "admin", "2025-01-01T00:00:00"),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(auth_db, "AUTH_DB_PATH", old_db_path)
    auth_db.init_auth_db()

    # Old data must survive the migration.
    migrated = auth_db.get_user_by_username_and_source("existing-user", "local")
    assert migrated is not None
    assert migrated["role"] == "admin"

    # The new constraint must actually allow a same-named AD account now.
    auth_db.create_user("existing-user", "", role="user", auth_source="ad")
    ad_version = auth_db.get_user_by_username_and_source("existing-user", "ad")
    assert ad_version is not None
    assert ad_version["id"] != migrated["id"]