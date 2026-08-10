"""
SQLite storage for routing tables and host interfaces.

Schema:
  hosts(id, name UNIQUE, updated_at)
  routes(id, host_id -> hosts.id, network, next_hop, interface)
  interfaces(id, host_id -> hosts.id, name, ip_address, description)

Each route is a CIDR network address ("network"), a next-hop IP address or
the literal string "directly connected" ("next_hop"), and an optional
egress interface name. Each interface has a name, CIDR address, and optional
description — typically filled from "C … is directly connected, <iface>"
lines when importing device output.

Saving a host's table replaces its entire set of routes and interfaces.
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
        # Migration: databases created before "interface" existed won't have
        # this column yet — add it in place rather than requiring anyone to
        # delete/recreate toolbox.db.
        existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(routes)").fetchall()}
        if "interface" not in existing_cols:
            conn.execute("ALTER TABLE routes ADD COLUMN interface TEXT")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ipam_subnets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cidr TEXT NOT NULL UNIQUE,
                vlan INTEGER,
                description TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ipam_addresses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subnet_id INTEGER NOT NULL REFERENCES ipam_subnets(id) ON DELETE CASCADE,
                address TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'used',
                hostname TEXT,
                description TEXT,
                updated_at TEXT NOT NULL,
                UNIQUE(subnet_id, address)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    # Hosts saved before interface inventory existed still have connected
    # routes with an interface name — materialize those into the interfaces table.
    backfill_interfaces_from_routes()


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


def _route_dict(row: sqlite3.Row) -> Dict:
    return {"network": row["network"], "nextHop": row["next_hop"], "interface": row["interface"]}


def _interface_dict(row: sqlite3.Row) -> Dict:
    return {"name": row["name"], "ipAddress": row["ip_address"], "description": row["description"]}


def interfaces_from_connected_routes(routes: List[Dict]) -> List[Dict]:
    """Build interface entries from routes whose next hop is 'directly connected'."""
    result = []
    seen = set()
    for r in routes:
        if (r.get("nextHop") or "").strip().lower() != DIRECTLY_CONNECTED:
            continue
        name = (r.get("interface") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        result.append({"name": name, "ipAddress": r["network"], "description": None})
    return result


def merge_interfaces(stored: List[Dict], routes: List[Dict]) -> List[Dict]:
    """Prefer explicit interface rows; fill gaps from connected routes."""
    by_name = {}
    order = []
    for i in stored or []:
        name = (i.get("name") or "").strip()
        if not name or name in by_name:
            continue
        by_name[name] = i
        order.append(name)
    for i in interfaces_from_connected_routes(routes):
        name = i["name"]
        if name in by_name:
            continue
        by_name[name] = i
        order.append(name)
    return [by_name[n] for n in order]


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
        interface_rows = conn.execute(
            "SELECT name, ip_address, description FROM interfaces WHERE host_id = ? ORDER BY id",
            (host_row["id"],),
        ).fetchall()
        routes = [_route_dict(r) for r in route_rows]
        stored = [_interface_dict(i) for i in interface_rows]
        return {
            "host": host_row["name"],
            "updatedAt": host_row["updated_at"],
            "routes": routes,
            "interfaces": merge_interfaces(stored, routes),
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
                "SELECT network, next_hop, interface FROM routes WHERE host_id = ? ORDER BY id",
                (h["id"],),
            ).fetchall()
            interface_rows = conn.execute(
                "SELECT name, ip_address, description FROM interfaces WHERE host_id = ? ORDER BY id",
                (h["id"],),
            ).fetchall()
            routes = [_route_dict(r) for r in route_rows]
            stored = [_interface_dict(i) for i in interface_rows]
            result.append(
                {
                    "host": h["name"],
                    "updatedAt": h["updated_at"],
                    "routes": routes,
                    "interfaces": merge_interfaces(stored, routes),
                }
            )
        return result
    finally:
        conn.close()


def save_host(host: str, routes: List[Dict], interfaces: Optional[List[Dict]] = None) -> Dict:
    if interfaces is None:
        interfaces = []

    # Always keep connected-route interfaces in the inventory, even if the
    # client omitted the % lines (e.g. hosts saved before this existed).
    interfaces = merge_interfaces(interfaces, routes)

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
        conn.executemany(
            "INSERT INTO routes (host_id, network, next_hop, interface) VALUES (?, ?, ?, ?)",
            [(host_id, r["network"], r["nextHop"], r.get("interface") or None) for r in routes],
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


def backfill_interfaces_from_routes() -> int:
    """Persist interface rows derived from connected routes for hosts that lack them."""
    updated = 0
    for summary in list_hosts():
        if summary["interfaceCount"] > 0:
            continue
        detail = get_host(summary["host"])
        if detail is None:
            continue
        derived = interfaces_from_connected_routes(detail["routes"])
        if not derived:
            continue
        save_host(detail["host"], detail["routes"], detail["interfaces"])
        updated += 1
    return updated


def delete_host(host: str) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM hosts WHERE name = ?", (host,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# IPAM — subnets (with an optional VLAN tag) and the individual IP addresses
# recorded within them (status + hostname/DNS name + description).
#
# Subnets are a logical container, not a pre-populated list of every address
# in the range — admins record addresses as they allocate/reserve/free them,
# same philosophy as routes/interfaces above (explicit rows, not derived).
# ---------------------------------------------------------------------------

IPAM_STATUSES = ("used", "free", "reserved")


def validate_cidr(cidr: str) -> str:
    """Validate a subnet CIDR and normalize it to its network address (e.g. '10.0.1.5/24' -> '10.0.1.0/24')."""
    try:
        return str(ipaddress.ip_network(cidr.strip(), strict=False))
    except ValueError:
        raise ValueError(f'"{cidr}" is not a valid network in CIDR notation')


def validate_vlan(vlan: Optional[int]) -> None:
    if vlan is None:
        return
    if not (1 <= vlan <= 4094):
        raise ValueError(f'VLAN {vlan} is out of range (must be 1-4094)')


def validate_status(status: str) -> None:
    if status not in IPAM_STATUSES:
        raise ValueError(f'"{status}" is not a valid status (use one of: {", ".join(IPAM_STATUSES)})')


def validate_address_in_subnet(address: str, cidr: str) -> None:
    try:
        ip = ipaddress.ip_address(address.strip())
    except ValueError:
        raise ValueError(f'"{address}" is not a valid IP address')
    if ip not in ipaddress.ip_network(cidr):
        raise ValueError(f'"{address}" is not inside subnet {cidr}')


def _address_sort_key(row: Dict) -> tuple:
    return (ipaddress.ip_address(row["address"]).version, ipaddress.ip_address(row["address"]))


def _subnet_summary(conn: sqlite3.Connection, row: sqlite3.Row) -> Dict:
    counts = {"used": 0, "free": 0, "reserved": 0}
    for r in conn.execute(
        "SELECT status, COUNT(*) AS n FROM ipam_addresses WHERE subnet_id = ? GROUP BY status", (row["id"],)
    ).fetchall():
        counts[r["status"]] = r["n"]
    total = ipaddress.ip_network(row["cidr"]).num_addresses
    return {
        "id": row["id"],
        "cidr": row["cidr"],
        "vlan": row["vlan"],
        "description": row["description"],
        "updatedAt": row["updated_at"],
        "totalAddresses": total,
        "usedCount": counts["used"],
        "freeCount": counts["free"],
        "reservedCount": counts["reserved"],
        "recordedCount": counts["used"] + counts["free"] + counts["reserved"],
    }


def list_subnets() -> List[Dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM ipam_subnets ORDER BY cidr COLLATE NOCASE").fetchall()
        subnets = [_subnet_summary(conn, r) for r in rows]
        # Numeric-ish sort by network address rather than plain text CIDR sort.
        subnets.sort(key=lambda s: (ipaddress.ip_network(s["cidr"]).version, ipaddress.ip_network(s["cidr"])))
        return subnets
    finally:
        conn.close()


def _address_dict(row: sqlite3.Row) -> Dict:
    return {
        "id": row["id"],
        "address": row["address"],
        "status": row["status"],
        "hostname": row["hostname"],
        "description": row["description"],
        "updatedAt": row["updated_at"],
    }


def get_subnet(subnet_id: int) -> Optional[Dict]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM ipam_subnets WHERE id = ?", (subnet_id,)).fetchone()
        if row is None:
            return None
        summary = _subnet_summary(conn, row)
        addr_rows = conn.execute(
            "SELECT * FROM ipam_addresses WHERE subnet_id = ?", (subnet_id,)
        ).fetchall()
        addresses = [_address_dict(r) for r in addr_rows]
        addresses.sort(key=_address_sort_key)
        summary["addresses"] = addresses
        return summary
    finally:
        conn.close()


def create_subnet(cidr: str, vlan: Optional[int] = None, description: Optional[str] = None) -> Dict:
    cidr = validate_cidr(cidr)
    validate_vlan(vlan)
    conn = get_connection()
    try:
        try:
            cur = conn.execute(
                "INSERT INTO ipam_subnets (cidr, vlan, description, updated_at) VALUES (?, ?, ?, ?)",
                (cidr, vlan, description, _now()),
            )
        except sqlite3.IntegrityError:
            raise ValueError(f'Subnet "{cidr}" already exists')
        conn.commit()
        subnet_id = cur.lastrowid
    finally:
        conn.close()
    return get_subnet(subnet_id)


def update_subnet(subnet_id: int, cidr: str, vlan: Optional[int] = None, description: Optional[str] = None) -> Dict:
    cidr = validate_cidr(cidr)
    validate_vlan(vlan)
    conn = get_connection()
    try:
        existing = conn.execute("SELECT id FROM ipam_subnets WHERE id = ?", (subnet_id,)).fetchone()
        if existing is None:
            raise ValueError("Subnet not found")
        # If the range is shrinking, refuse to silently orphan addresses that
        # would fall outside the new CIDR — make the admin deal with them first.
        addr_rows = conn.execute(
            "SELECT address FROM ipam_addresses WHERE subnet_id = ?", (subnet_id,)
        ).fetchall()
        network = ipaddress.ip_network(cidr)
        outside = [r["address"] for r in addr_rows if ipaddress.ip_address(r["address"]) not in network]
        if outside:
            raise ValueError(
                f"Can't resize to {cidr} — {len(outside)} recorded address(es) would fall outside it "
                f"(e.g. {outside[0]}). Remove or move them first."
            )
        try:
            conn.execute(
                "UPDATE ipam_subnets SET cidr = ?, vlan = ?, description = ?, updated_at = ? WHERE id = ?",
                (cidr, vlan, description, _now(), subnet_id),
            )
        except sqlite3.IntegrityError:
            raise ValueError(f'Subnet "{cidr}" already exists')
        conn.commit()
    finally:
        conn.close()
    return get_subnet(subnet_id)


def delete_subnet(subnet_id: int) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM ipam_subnets WHERE id = ?", (subnet_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def add_address(
    subnet_id: int, address: str, status: str = "used", hostname: Optional[str] = None, description: Optional[str] = None
) -> Dict:
    conn = get_connection()
    try:
        subnet_row = conn.execute("SELECT cidr FROM ipam_subnets WHERE id = ?", (subnet_id,)).fetchone()
        if subnet_row is None:
            raise ValueError("Subnet not found")
        validate_address_in_subnet(address, subnet_row["cidr"])
        validate_status(status)
        address = str(ipaddress.ip_address(address.strip()))
        try:
            conn.execute(
                """
                INSERT INTO ipam_addresses (subnet_id, address, status, hostname, description, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (subnet_id, address, status, hostname, description, _now()),
            )
        except sqlite3.IntegrityError:
            raise ValueError(f'"{address}" is already recorded in this subnet')
        conn.commit()
    finally:
        conn.close()
    return get_subnet(subnet_id)


def update_address(
    subnet_id: int,
    address_id: int,
    address: str,
    status: str = "used",
    hostname: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict:
    conn = get_connection()
    try:
        subnet_row = conn.execute("SELECT cidr FROM ipam_subnets WHERE id = ?", (subnet_id,)).fetchone()
        if subnet_row is None:
            raise ValueError("Subnet not found")
        existing = conn.execute(
            "SELECT id FROM ipam_addresses WHERE id = ? AND subnet_id = ?", (address_id, subnet_id)
        ).fetchone()
        if existing is None:
            raise ValueError("Address not found")
        validate_address_in_subnet(address, subnet_row["cidr"])
        validate_status(status)
        address = str(ipaddress.ip_address(address.strip()))
        try:
            conn.execute(
                """
                UPDATE ipam_addresses
                SET address = ?, status = ?, hostname = ?, description = ?, updated_at = ?
                WHERE id = ? AND subnet_id = ?
                """,
                (address, status, hostname, description, _now(), address_id, subnet_id),
            )
        except sqlite3.IntegrityError:
            raise ValueError(f'"{address}" is already recorded in this subnet')
        conn.commit()
    finally:
        conn.close()
    return get_subnet(subnet_id)


def delete_address(subnet_id: int, address_id: int) -> Dict:
    conn = get_connection()
    try:
        subnet_row = conn.execute("SELECT id FROM ipam_subnets WHERE id = ?", (subnet_id,)).fetchone()
        if subnet_row is None:
            raise ValueError("Subnet not found")
        conn.execute("DELETE FROM ipam_addresses WHERE id = ? AND subnet_id = ?", (address_id, subnet_id))
        conn.commit()
    finally:
        conn.close()
    return get_subnet(subnet_id)
