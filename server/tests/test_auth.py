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
    res = client.post("/api/admin/users", json={"username": "erin", "password": "pw123", "role": "user"})
    assert res.status_code == 200
    assert res.json()["username"] == "erin"
    assert "passwordHash" not in res.json()
    assert "password" not in res.json()


def test_create_user_rejects_duplicate_username(client):
    client.post("/api/admin/users", json={"username": "frank", "password": "pw1"})
    res = client.post("/api/admin/users", json={"username": "frank", "password": "pw2"})
    assert res.status_code == 400


def test_delete_user(client):
    created = client.post("/api/admin/users", json={"username": "gina", "password": "pw"}).json()
    res = client.delete(f"/api/admin/users/{created['id']}")
    assert res.status_code == 200
    remaining = [u["username"] for u in client.get("/api/admin/users").json()]
    assert "gina" not in remaining


def test_cannot_delete_last_admin(client):
    import auth_db
    for u in auth_db.list_users():
        if u["role"] == "admin":
            auth_db.delete_user(u["id"])
    admin = client.post("/api/admin/users", json={"username": "only-admin", "password": "pw", "role": "admin"}).json()
    res = client.delete(f"/api/admin/users/{admin['id']}")
    assert res.status_code == 400


def test_reset_password_lets_user_log_in_with_new_password(client):
    created = client.post("/api/admin/users", json={"username": "helen", "password": "old-pw"}).json()
    client.post(f"/api/admin/users/{created['id']}/reset-password", json={"newPassword": "new-pw"})
    res = client.post("/api/auth/login", json={"username": "helen", "password": "new-pw"})
    assert res.status_code == 200


def test_cannot_enable_login_without_being_logged_in_as_admin(client):
    import auth_db
    auth_db.set_setting("require_login", "false")
    res = client.post("/api/admin/settings/require-login", json={"enabled": True})
    assert res.status_code == 403
    assert auth_db.is_login_required() is False


def test_can_enable_login_when_logged_in_as_admin(client):
    import auth_db, auth
    auth_db.set_setting("require_login", "false")
    auth_db.create_user("ivan", auth.hash_password("pw"), role="admin")
    client.post("/api/auth/login", json={"username": "ivan", "password": "pw"})
    res = client.post("/api/admin/settings/require-login", json={"enabled": True})
    assert res.status_code == 200
    assert auth_db.is_login_required() is True
    auth_db.set_setting("require_login", "false")


def test_non_admin_cannot_disable_login_once_enabled(client):
    import auth_db, auth
    auth_db.set_setting("require_login", "false")
    auth_db.create_user("judy", auth.hash_password("pw"), role="user")
    client.post("/api/auth/login", json={"username": "judy", "password": "pw"})
    auth_db.set_setting("require_login", "true")
    res = client.post("/api/admin/settings/require-login", json={"enabled": False})
    assert res.status_code == 403
    auth_db.set_setting("require_login", "false")