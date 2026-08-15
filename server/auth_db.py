"""
Separate SQLite database for authentication data (users, sessions,
app settings). Deliberately kept apart from toolbox.db in db.py so
credentials never live in the same file as application data.
"""
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import auth

AUTH_DB_PATH = Path(__file__).parent / "auth.db"


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