"""
Separate SQLite database for authentication data (users, sessions,
app settings). Deliberately kept apart from toolbox.db in db.py so
credentials never live in the same file as application data.
"""
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import auth

AUTH_DB_PATH = Path(__file__).parent / "auth.db"

# The "admin" role is hardcoded infrastructure (see require_admin_user in
# main.py, count_admin_users below, etc.) — it always has full access to
# every tool plus the Config Panel, can't be renamed/deleted, and its
# permission list is never read from the database.
ADMIN_ROLE_NAME = "admin"
FULL_ACCESS_PERMISSIONS = ["*"]

# The default non-admin role, seeded once on first startup. Given every
# permission at seed time so existing single-role deployments keep working
# exactly as before until an admin deliberately narrows it down.
DEFAULT_ROLE_NAME = "user"
DEFAULT_ROLE_SEED_PERMISSIONS = [
    "subnet-splitter",
    "connection-test",
    "routing-map",
    "ip-calculator",
    "ipam",
]


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(AUTH_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_auth_db() -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                permissions TEXT NOT NULL DEFAULT '[]',
                is_builtin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()

        # Seed the two built-in roles once. "admin" is a sentinel handled in
        # code (see ADMIN_ROLE_NAME above) — its stored permissions column is
        # never consulted, but the row exists so it shows up in role listings
        # and so foreign-key-style lookups by name always find something.
        existing = {
            row["name"] for row in conn.execute("SELECT name FROM roles").fetchall()
        }
        if ADMIN_ROLE_NAME not in existing:
            conn.execute(
                "INSERT INTO roles (name, permissions, is_builtin, created_at) VALUES (?, ?, 1, ?)",
                (ADMIN_ROLE_NAME, json.dumps(FULL_ACCESS_PERMISSIONS), _now()),
            )
        if DEFAULT_ROLE_NAME not in existing:
            conn.execute(
                "INSERT INTO roles (name, permissions, is_builtin, created_at) VALUES (?, ?, 1, ?)",
                (DEFAULT_ROLE_NAME, json.dumps(DEFAULT_ROLE_SEED_PERMISSIONS), _now()),
            )
        conn.commit()
    finally:
        conn.close()


def _user_dict(row: sqlite3.Row) -> Dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "passwordHash": row["password_hash"],
        "role": row["role"],
        "createdAt": row["created_at"],
    }


def create_user(username: str, password_hash: str, role: str = "user") -> Dict:
    conn = get_connection()
    try:
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                (username, password_hash, role, _now()),
            )
        except sqlite3.IntegrityError:
            raise ValueError(f'Username "{username}" is already taken')
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return _user_dict(row)
    finally:
        conn.close()


def get_user_by_username(username: str) -> Optional[Dict]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return _user_dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> Optional[Dict]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _user_dict(row) if row else None
    finally:
        conn.close()


def create_session(user_id: int, token: str) -> None:
    conn = get_connection()
    try:
        token_hash = auth.hash_token(token)
        created_at = datetime.now(timezone.utc)
        expires_at = created_at + timedelta(days=auth.SESSION_TTL_DAYS)
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token_hash, user_id, created_at.isoformat(), expires_at.isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def get_user_by_session_token(token: str) -> Optional[Dict]:
    conn = get_connection()
    try:
        token_hash = auth.hash_token(token)
        row = conn.execute(
            "SELECT * FROM sessions WHERE token_hash = ?", (token_hash,)
        ).fetchone()
        if row is None:
            return None
        if row["expires_at"] < datetime.now(timezone.utc).isoformat():
            return None
        user_row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (row["user_id"],)
        ).fetchone()
        return _user_dict(user_row) if user_row else None
    finally:
        conn.close()


def delete_session_by_token(token: str) -> None:
    conn = get_connection()
    try:
        token_hash = auth.hash_token(token)
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
        conn.commit()
    finally:
        conn.close()


def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_setting(key: str, value: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def is_login_required() -> bool:
    return get_setting("require_login", "false") == "true"


def list_users() -> List[Dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM users ORDER BY username").fetchall()
        return [_user_dict(row) for row in rows]
    finally:
        conn.close()


def count_admin_users() -> int:
    conn = get_connection()
    try:
        row = conn.execute("SELECT COUNT(*) AS c FROM users WHERE role = 'admin'").fetchone()
        return row["c"]
    finally:
        conn.close()


def delete_user(user_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def update_user_password(user_id: int, password_hash: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (password_hash, user_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_user_role(user_id: int, role: str) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Roles — each non-admin role carries a customizable list of tool ids it
# grants access to. The "admin" role is a sentinel: it always means full
# access (see ADMIN_ROLE_NAME) and is never edited through these functions.
# ---------------------------------------------------------------------------

def _role_dict(row: sqlite3.Row) -> Dict:
    name = row["name"]
    if name == ADMIN_ROLE_NAME:
        permissions = list(FULL_ACCESS_PERMISSIONS)
    else:
        try:
            permissions = json.loads(row["permissions"])
        except (TypeError, ValueError):
            permissions = []
    return {
        "id": row["id"],
        "name": name,
        "permissions": permissions,
        "isBuiltin": bool(row["is_builtin"]),
    }


def list_roles() -> List[Dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM roles ORDER BY is_builtin DESC, name").fetchall()
        return [_role_dict(row) for row in rows]
    finally:
        conn.close()


def get_role_by_name(name: str) -> Optional[Dict]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM roles WHERE name = ?", (name,)).fetchone()
        return _role_dict(row) if row else None
    finally:
        conn.close()


def get_role_by_id(role_id: int) -> Optional[Dict]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM roles WHERE id = ?", (role_id,)).fetchone()
        return _role_dict(row) if row else None
    finally:
        conn.close()


def role_permissions_for_name(role_name: str) -> List[str]:
    """Permissions for a role name, used to gate feature access. Falls back
    to no access if the role no longer exists (e.g. it was deleted out from
    under a user), rather than silently granting anything."""
    if role_name == ADMIN_ROLE_NAME:
        return list(FULL_ACCESS_PERMISSIONS)
    role = get_role_by_name(role_name)
    return role["permissions"] if role else []


def create_role(name: str, permissions: List[str]) -> Dict:
    name = name.strip()
    if not name:
        raise ValueError("Role name is required")
    if name == ADMIN_ROLE_NAME:
        raise ValueError('"admin" is a reserved role name')
    conn = get_connection()
    try:
        try:
            conn.execute(
                "INSERT INTO roles (name, permissions, is_builtin, created_at) VALUES (?, ?, 0, ?)",
                (name, json.dumps(permissions), _now()),
            )
        except sqlite3.IntegrityError:
            raise ValueError(f'Role "{name}" already exists')
        conn.commit()
        row = conn.execute("SELECT * FROM roles WHERE name = ?", (name,)).fetchone()
        return _role_dict(row)
    finally:
        conn.close()


def update_role_permissions(role_id: int, permissions: List[str]) -> Dict:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM roles WHERE id = ?", (role_id,)).fetchone()
        if row is None:
            raise ValueError("Role not found")
        if row["name"] == ADMIN_ROLE_NAME:
            raise ValueError('The "admin" role always has full access and cannot be edited')
        conn.execute(
            "UPDATE roles SET permissions = ? WHERE id = ?",
            (json.dumps(permissions), role_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM roles WHERE id = ?", (role_id,)).fetchone()
        return _role_dict(row)
    finally:
        conn.close()


def count_users_with_role(role_name: str) -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE role = ?", (role_name,)
        ).fetchone()
        return row["c"]
    finally:
        conn.close()


def delete_role(role_id: int) -> None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM roles WHERE id = ?", (role_id,)).fetchone()
        if row is None:
            raise ValueError("Role not found")
        if row["name"] == ADMIN_ROLE_NAME:
            raise ValueError('The "admin" role cannot be deleted')
        if count_users_with_role(row["name"]) > 0:
            raise ValueError(
                f'Role "{row["name"]}" is still assigned to one or more users'
            )
        conn.execute("DELETE FROM roles WHERE id = ?", (role_id,))
        conn.commit()
    finally:
        conn.close()