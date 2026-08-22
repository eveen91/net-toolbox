import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent / "toolbox.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                mgmt_ip TEXT NOT NULL,
                vendor TEXT NOT NULL,
                model TEXT NOT NULL,
                os_version TEXT,
                device_type TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


def list_devices():
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, name, mgmt_ip, vendor, model, os_version, device_type, updated_at FROM devices ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "mgmtIp": row["mgmt_ip"],
                "vendor": row["vendor"],
                "model": row["model"],
                "osVersion": row["os_version"],
                "deviceType": row["device_type"],
                "updatedAt": row["updated_at"],
            }
            for row in rows
        ]
    finally:
        conn.close()


def add_device(name, mgmt_ip, vendor, model, os_version, device_type):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO devices (name, mgmt_ip, vendor, model, os_version, device_type, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, mgmt_ip, vendor, model, os_version, device_type, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise ValueError(f'Device "{name}" already exists')
    finally:
        conn.close()
    return list_devices()


def update_device(device_id, name, mgmt_ip, vendor, model, os_version, device_type):
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE devices SET name = ?, mgmt_ip = ?, vendor = ?, model = ?, os_version = ?, device_type = ?, updated_at = ? WHERE id = ?",
            (name, mgmt_ip, vendor, model, os_version, device_type, datetime.now(timezone.utc).isoformat(), device_id),
        )
        conn.commit()
    finally:
        conn.close()
    return list_devices()


def delete_device(device_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
        conn.commit()
    finally:
        conn.close()
    return list_devices()
