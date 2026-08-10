"""
SQLite storage for routing tables and host interfaces.

Schema:
  hosts(id, name UNIQUE, updated_at)
  routes(id, host_id -> hosts.id, network, next_hop)
  interfaces(id, host_id -> hosts.id, name, ip_address, description)

Each route is a CIDR network address ("network") and a next-hop IP address
("next_hop"). Each interface has a name, CIDR IP address, and optional description.
Saving a host's table replaces its entire set of routes and interfaces.
"""

import ipaddress
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).parent / "toolbox.db"


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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS interfaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                host_id INTEGER NOT NULL REFERENCES hosts(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                description TEXT
            )
            """
        )
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
    try:
        ipaddress.ip_address(next_hop)
    except ValueError:
        raise ValueError(f'"{next_hop}" is not a valid next-hop IP address')


def validate_interface(name: str, ip_address: str) -> None:
    if not name or not name.strip():
        raise ValueError("Interface name must be non-empty")
    try:
        ipaddress.ip_interface(ip_address)
    except ValueError:
        raise ValueError(f'"{ip_address}" is not a valid IP interface in CIDR notation')


def list_hosts() -> List[Dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT
                h.name AS host,
                h.updated_at AS updated_at,
                (SELECT COUNT(*) FROM routes WHERE host_id = h.id) AS route_count,
                (SELECT COUNT(*) FROM interfaces WHERE host_id = h.id) AS interface_count
            FROM hosts h
            ORDER BY h.name COLLATE NOCASE
            """
        ).fetchall()
        return [
            {
                "host": row["host"],
                "updatedAt": row["updated_at"],
                "routeCount": row["route_count"],
                "interfaceCount": row["interface_count"],
            }
            for row in rows
        ]
    finally:
        conn.close()


def get_host(host: str) -> Optional[Dict]:
    conn = get_connection()
    try:
        host_row = conn.execute(
            "SELECT id, name, updated_at FROM hosts WHERE name = ?", (host,)
        ).fetchone()
        if host_row is None:
            return None
        route_rows = conn.execute(
            "SELECT network, next_hop FROM routes WHERE host_id = ? ORDER BY id",
            (host_row["id"],),
        ).fetchall()
        interface_rows = conn.execute(
            "SELECT name, ip_address, description FROM interfaces WHERE host_id = ? ORDER BY id",
            (host_row["id"],),
        ).fetchall()
        return {
            "host": host_row["name"],
            "updatedAt": host_row["updated_at"],
            "routes": [{"network": r["network"], "nextHop": r["next_hop"]} for r in route_rows],
            "interfaces": [
                {"name": i["name"], "ipAddress": i["ip_address"], "description": i["description"]}
                for i in interface_rows
            ],
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
                "SELECT network, next_hop FROM routes WHERE host_id = ? ORDER BY id", (h["id"],)
            ).fetchall()
            interface_rows = conn.execute(
                "SELECT name, ip_address, description FROM interfaces WHERE host_id = ? ORDER BY id",
                (h["id"],),
            ).fetchall()
            result.append(
                {
                    "host": h["name"],
                    "updatedAt": h["updated_at"],
                    "routes": [
                        {"network": r["network"], "nextHop": r["next_hop"]} for r in route_rows
                    ],
                    "interfaces": [
                        {"name": i["name"], "ipAddress": i["ip_address"], "description": i["description"]}
                        for i in interface_rows
                    ],
                }
            )
        return result
    finally:
        conn.close()


def save_host(host: str, routes: List[Dict], interfaces: Optional[List[Dict]] = None) -> Dict:
    if interfaces is None:
        interfaces = []

    for r in routes:
        validate_route(r["network"], r["nextHop"])

    for i in interfaces:
        validate_interface(i["name"], i["ipAddress"])

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
        conn.execute("DELETE FROM interfaces WHERE host_id = ?", (host_id,))

        if routes:
            conn.executemany(
                "INSERT INTO routes (host_id, network, next_hop) VALUES (?, ?, ?)",
                [(host_id, r["network"], r["nextHop"]) for r in routes],
            )

        if interfaces:
            conn.executemany(
                "INSERT INTO interfaces (host_id, name, ip_address, description) VALUES (?, ?, ?, ?)",
                [(host_id, i["name"], i["ipAddress"], i.get("description")) for i in interfaces],
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
