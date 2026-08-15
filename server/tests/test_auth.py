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