"""
SQLite storage for routing tables.

Schema:
  hosts(id, name UNIQUE, updated_at)
  routes(id, host_id -> hosts.id, network, next_hop, interface)

Each route is a CIDR network address ("network"), a next-hop IP address or
the literal string "directly connected" ("next_hop"), and an optional
interface name. Saving a host's routes replaces its entire route set — this
matches how the UI works (edit a host's routing table as a whole, then save).

One connection is opened per call and closed immediately after — simple and
safe for this tool's read-heavy, low-concurrency access pattern. If this ever
needs to handle a lot of concurrent writers, that's the point to switch to a
pooled connection or a heavier database (see README).
"""

import ipaddress
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).parent / "toolbox.db"

DIRECTLY_CONNECTED = "directly connected"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hosts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS routes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                host_id INTEGER NOT NULL REFERENCES hosts(id) ON DELETE CASCADE,
                network TEXT NOT NULL,
                next_hop TEXT NOT NULL
            )
            """
        )
        # Migration: databases created before "interface" existed won't have
        # this column yet — add it in place rather than requiring anyone to
        # delete/recreate toolbox.db.
        existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(routes)").fetchall()}
        if "interface" not in existing_cols:
            conn.execute("ALTER TABLE routes ADD COLUMN interface TEXT")
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_route(network: str, next_hop: str) -> None:
    try:
        ipaddress.ip_network(network, strict=False)
    except ValueError:
        raise ValueError(f'"{network}" is not a valid network in CIDR notation')
    if next_hop.strip().lower() != DIRECTLY_CONNECTED:
        try:
            ipaddress.ip_address(next_hop)
        except ValueError:
            raise ValueError(
                f'"{next_hop}" is not a valid next-hop IP address (use "{DIRECTLY_CONNECTED}" for local routes)'
            )


def list_hosts() -> List[Dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT h.name AS host, h.updated_at AS updated_at, COUNT(r.id) AS route_count
            FROM hosts h
            LEFT JOIN routes r ON r.host_id = h.id
            GROUP BY h.id
            ORDER BY h.name COLLATE NOCASE
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _route_dict(row: sqlite3.Row) -> Dict:
    return {"network": row["network"], "nextHop": row["next_hop"], "interface": row["interface"]}


def get_host(host: str) -> Optional[Dict]:
    conn = get_connection()
    try:
        host_row = conn.execute(
            "SELECT id, name, updated_at FROM hosts WHERE name = ?", (host,)
        ).fetchone()
        if host_row is None:
            return None
        route_rows = conn.execute(
            "SELECT network, next_hop, interface FROM routes WHERE host_id = ? ORDER BY id",
            (host_row["id"],),
        ).fetchall()
        return {
            "host": host_row["name"],
            "updatedAt": host_row["updated_at"],
            "routes": [_route_dict(r) for r in route_rows],
        }
    finally:
        conn.close()


def export_all() -> List[Dict]:
    conn = get_connection()
    try:
        host_rows = conn.execute(
            "SELECT id, name, updated_at FROM hosts ORDER BY name COLLATE NOCASE"
        ).fetchall()
        result = []
        for h in host_rows:
            route_rows = conn.execute(
                "SELECT network, next_hop, interface FROM routes WHERE host_id = ? ORDER BY id", (h["id"],)
            ).fetchall()
            result.append(
                {
                    "host": h["name"],
                    "updatedAt": h["updated_at"],
                    "routes": [_route_dict(r) for r in route_rows],
                }
            )
        return result
    finally:
        conn.close()


def save_host(host: str, routes: List[Dict]) -> Dict:
    for r in routes:
        validate_route(r["network"], r["nextHop"])

    conn = get_connection()
    try:
        now = _now()
        conn.execute(
            """
            INSERT INTO hosts (name, updated_at) VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET updated_at = excluded.updated_at
            """,
            (host, now),
        )
        host_id = conn.execute("SELECT id FROM hosts WHERE name = ?", (host,)).fetchone()["id"]
        conn.execute("DELETE FROM routes WHERE host_id = ?", (host_id,))
        conn.executemany(
            "INSERT INTO routes (host_id, network, next_hop, interface) VALUES (?, ?, ?, ?)",
            [(host_id, r["network"], r["nextHop"], r.get("interface") or None) for r in routes],
        )
        conn.commit()
    finally:
        conn.close()
    return get_host(host)


def delete_host(host: str) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM hosts WHERE name = ?", (host,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
