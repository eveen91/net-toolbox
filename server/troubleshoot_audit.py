import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent / "toolbox.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_name TEXT,
                command TEXT NOT NULL,
                username TEXT,
                success INTEGER NOT NULL,
                error TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


def log_command(device_name, command, username, success, error):
    try:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO audit_log (device_name, command, username, success, error, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (device_name, command, username, 1 if success else 0, error, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def get_recent_audit_log(limit=50):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, device_name, command, username, success, error, created_at FROM audit_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "deviceName": row["device_name"],
                "command": row["command"],
                "username": row["username"],
                "success": bool(row["success"]),
                "error": row["error"],
                "createdAt": row["created_at"],
            }
            for row in rows
        ]
    finally:
        conn.close()
