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
import json
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
                parent_id INTEGER REFERENCES ipam_subnets(id),
                updated_at TEXT NOT NULL
            )
            """
        )
        # Migration: databases created before nesting existed won't have this
        # column yet — add it in place rather than requiring a fresh DB.
        subnet_cols = {row["name"] for row in conn.execute("PRAGMA table_info(ipam_subnets)").fetchall()}
        if "parent_id" not in subnet_cols:
            conn.execute("ALTER TABLE ipam_subnets ADD COLUMN parent_id INTEGER REFERENCES ipam_subnets(id)")
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
        # Migration: databases created before nested subnets existed won't
        # have this column yet — add it in place, same as the "interface"
        # migration above.
        ipam_cols = {row["name"] for row in conn.execute("PRAGMA table_info(ipam_subnets)").fetchall()}
        if "parent_id" not in ipam_cols:
            conn.execute("ALTER TABLE ipam_subnets ADD COLUMN parent_id INTEGER REFERENCES ipam_subnets(id)")

        # Migration: add the host metadata columns (team / machine type / vm
        # cluster / environment) to databases created before they existed.
        ipam_addr_cols = {row["name"] for row in conn.execute("PRAGMA table_info(ipam_addresses)").fetchall()}
        if "team" not in ipam_addr_cols:
            conn.execute("ALTER TABLE ipam_addresses ADD COLUMN team TEXT")
        if "machine_type" not in ipam_addr_cols:
            conn.execute("ALTER TABLE ipam_addresses ADD COLUMN machine_type TEXT")
        if "vm_cluster" not in ipam_addr_cols:
            conn.execute("ALTER TABLE ipam_addresses ADD COLUMN vm_cluster TEXT")
        if "environment" not in ipam_addr_cols:
            conn.execute("ALTER TABLE ipam_addresses ADD COLUMN environment TEXT")
        if "locked" not in ipam_addr_cols:
            conn.execute("ALTER TABLE ipam_addresses ADD COLUMN locked INTEGER DEFAULT 0")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ipam_scan_excludes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subnet_id INTEGER NOT NULL REFERENCES ipam_subnets(id) ON DELETE CASCADE,
                address TEXT NOT NULL,
                UNIQUE(subnet_id, address)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ipam_scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subnet_id INTEGER NOT NULL REFERENCES ipam_subnets(id) ON DELETE CASCADE,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                scanned_count INTEGER NOT NULL,
                used_count INTEGER NOT NULL,
                free_count INTEGER NOT NULL,
                skipped_count INTEGER NOT NULL,
                newly_used_count INTEGER NOT NULL,
                went_quiet_count INTEGER NOT NULL,
                hostname_changed_count INTEGER NOT NULL,
                diff_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ipam_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

        conn.commit()

    finally:
        conn.close()

    # Populate/refresh parent_id for every subnet from its CIDR alone — cheap
    # and keeps hierarchy correct even for subnets that existed before nesting
    # was added, or if rows were ever edited outside the app.
    conn = get_connection()
    try:
        recompute_subnet_hierarchy(conn)
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
IPAM_MACHINE_TYPES = ("physical", "vm")
IPAM_ENVIRONMENTS = ("prod", "test", "dev")

# Maps the API's camelCase field names (as sent by BulkAddressUpdateRequest)
# to their actual ipam_addresses column names, for bulk_update_addresses.
BULK_ADDRESS_FIELD_COLUMNS = {
    "status": "status",
    "team": "team",
    "machineType": "machine_type",
    "vmCluster": "vm_cluster",
    "environment": "environment",
    "locked": "locked",
}


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


def validate_machine_type(machine_type: Optional[str]) -> None:
    if machine_type is None:
        return
    if machine_type not in IPAM_MACHINE_TYPES:
        raise ValueError(
            f'"{machine_type}" is not a valid machine type (use one of: {", ".join(IPAM_MACHINE_TYPES)})'
        )


def validate_environment(environment: Optional[str]) -> None:
    if environment is None:
        return
    if environment not in IPAM_ENVIRONMENTS:
        raise ValueError(
            f'"{environment}" is not a valid environment (use one of: {", ".join(IPAM_ENVIRONMENTS)})'
        )


def validate_address_in_subnet(address: str, cidr: str) -> None:
    try:
        ip = ipaddress.ip_address(address.strip())
    except ValueError:
        raise ValueError(f'"{address}" is not a valid IP address')
    if ip not in ipaddress.ip_network(cidr):
        raise ValueError(f'"{address}" is not inside subnet {cidr}')


def _address_sort_key(row: Dict) -> tuple:
    return (ipaddress.ip_address(row["address"]).version, ipaddress.ip_address(row["address"]))


def recompute_subnet_hierarchy(conn: sqlite3.Connection) -> None:
    """Derive parent_id for every subnet purely from its CIDR.

    CIDR blocks are always either disjoint or one is fully nested inside the
    other — never a partial overlap — so containment alone is enough to
    build the tree: a subnet's parent is the smallest other subnet whose
    range fully contains it. Call this after any insert/update/delete that
    touches ipam_subnets, before committing.
    """
    rows = conn.execute("SELECT id, cidr FROM ipam_subnets").fetchall()
    networks = {r["id"]: ipaddress.ip_network(r["cidr"]) for r in rows}
    updates = []
    for sid, net in networks.items():
        best_parent = None
        best_size = None
        for oid, onet in networks.items():
            if oid == sid or onet.version != net.version:
                continue
            if net.subnet_of(onet) and net != onet:
                if best_size is None or onet.num_addresses < best_size:
                    best_parent, best_size = oid, onet.num_addresses
        updates.append((best_parent, sid))
    conn.executemany("UPDATE ipam_subnets SET parent_id = ? WHERE id = ?", updates)


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
        "parentId": row["parent_id"],
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
        "team": row["team"],
        "machineType": row["machine_type"],
        "vmCluster": row["vm_cluster"],
        "environment": row["environment"],
        "locked": bool(row["locked"]),
        "updatedAt": row["updated_at"],
    }


def get_addresses_by_subnet(subnet_id: int) -> List[Dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM ipam_addresses WHERE subnet_id = ?", (subnet_id,)
        ).fetchall()
        return [_address_dict(r) for r in rows]
    finally:
        conn.close()


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
        subnet_id = cur.lastrowid
        # New subnet may nest inside an existing one, or become the new parent
        # of existing subnets it now contains — recompute the whole tree.
        recompute_subnet_hierarchy(conn)
        conn.commit()
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
        network = ipaddress.ip_network(cidr)

        # If the range is shrinking, refuse to silently orphan addresses that
        # would fall outside the new CIDR — make the admin deal with them first.
        addr_rows = conn.execute(
            "SELECT address FROM ipam_addresses WHERE subnet_id = ?", (subnet_id,)
        ).fetchall()
        outside_addrs = [r["address"] for r in addr_rows if ipaddress.ip_address(r["address"]) not in network]
        if outside_addrs:
            raise ValueError(
                f"Can't resize to {cidr} — {len(outside_addrs)} recorded address(es) would fall outside it "
                f"(e.g. {outside_addrs[0]}). Remove or move them first."
            )

        # Same idea for nested child subnets — don't let a resize silently
        # detach a child from its parent.
        child_rows = conn.execute("SELECT cidr FROM ipam_subnets WHERE parent_id = ?", (subnet_id,)).fetchall()
        outside_children = [
            r["cidr"] for r in child_rows if not ipaddress.ip_network(r["cidr"]).subnet_of(network)
        ]
        if outside_children:
            raise ValueError(
                f"Can't resize to {cidr} — it would no longer contain nested subnet(s): "
                f"{', '.join(outside_children)}. Resize or move them first."
            )

        try:
            conn.execute(
                "UPDATE ipam_subnets SET cidr = ?, vlan = ?, description = ?, updated_at = ? WHERE id = ?",
                (cidr, vlan, description, _now(), subnet_id),
            )
        except sqlite3.IntegrityError:
            raise ValueError(f'Subnet "{cidr}" already exists')
        recompute_subnet_hierarchy(conn)
        conn.commit()
    finally:
        conn.close()
    return get_subnet(subnet_id)


def delete_subnet(subnet_id: int) -> bool:
    conn = get_connection()
    try:
        # Detach children first — parent_id has no ON DELETE action, and we
        # want to recompute their new parent from scratch anyway.
        conn.execute("UPDATE ipam_subnets SET parent_id = NULL WHERE parent_id = ?", (subnet_id,))
        cur = conn.execute("DELETE FROM ipam_subnets WHERE id = ?", (subnet_id,))
        # Any subnets nested under the deleted one are promoted to its
        # parent (or to top-level if it had none) — recomputed purely from
        # the remaining CIDRs, same as everywhere else.
        recompute_subnet_hierarchy(conn)
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def add_address(
    subnet_id: int,
    address: str,
    status: str = "used",
    hostname: Optional[str] = None,
    description: Optional[str] = None,
    team: Optional[str] = None,
    machine_type: Optional[str] = None,
    vm_cluster: Optional[str] = None,
    environment: Optional[str] = None,
    locked: bool = False,
) -> Dict:
    conn = get_connection()
    try:
        subnet_row = conn.execute("SELECT cidr FROM ipam_subnets WHERE id = ?", (subnet_id,)).fetchone()
        if subnet_row is None:
            raise ValueError("Subnet not found")
        validate_address_in_subnet(address, subnet_row["cidr"])
        validate_status(status)
        validate_machine_type(machine_type)
        validate_environment(environment)
        if machine_type != "vm":
            vm_cluster = None
        address = str(ipaddress.ip_address(address.strip()))
        try:
            conn.execute(
                """
                INSERT INTO ipam_addresses
                    (subnet_id, address, status, hostname, description, team, machine_type, vm_cluster, environment, locked, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (subnet_id, address, status, hostname, description, team, machine_type, vm_cluster, environment, locked, _now()),
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
    team: Optional[str] = None,
    machine_type: Optional[str] = None,
    vm_cluster: Optional[str] = None,
    environment: Optional[str] = None,
    locked: bool = False,
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
        validate_machine_type(machine_type)
        validate_environment(environment)
        if machine_type != "vm":
            vm_cluster = None
        address = str(ipaddress.ip_address(address.strip()))
        try:
            conn.execute(
                """
                UPDATE ipam_addresses
                SET address = ?, status = ?, hostname = ?, description = ?,
                    team = ?, machine_type = ?, vm_cluster = ?, environment = ?, locked = ?, updated_at = ?
                WHERE id = ? AND subnet_id = ?
                """,
                (
                    address, status, hostname, description,
                    team, machine_type, vm_cluster, environment, locked,
                    _now(), address_id, subnet_id,
                ),
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


def bulk_update_addresses(subnet_id: int, address_ids: List[int], fields: Dict) -> Dict:
    """
    Apply the same field updates to many addresses within one subnet, in a
    single transaction.

    `fields` must contain ONLY the keys the caller actually wants to
    change (API-style camelCase: status/team/machineType/vmCluster/
    environment/locked) - a key's mere presence in `fields` means "set
    this column", matching the exclude_unset contract of
    BulkAddressUpdateRequest. Never assume any particular key is present.

    address_ids not belonging to subnet_id are silently skipped (the
    WHERE clause simply won't match them) rather than raising.
    """
    fields = dict(fields)  # don't mutate the caller's dict

    if "status" in fields:
        validate_status(fields["status"])
    if "machineType" in fields:
        validate_machine_type(fields["machineType"])
    if "environment" in fields:
        validate_environment(fields["environment"])

    # Same force-null-vm_cluster rule as add_address/update_address: setting
    # machineType to anything other than "vm" clears vm_cluster too - unless
    # the caller ALSO explicitly sent vmCluster, in which case their
    # explicit value wins over the force-null rule.
    if "machineType" in fields and fields["machineType"] != "vm" and "vmCluster" not in fields:
        fields["vmCluster"] = None

    set_columns = []
    params: List = []
    for api_key, column in BULK_ADDRESS_FIELD_COLUMNS.items():
        if api_key in fields:
            set_columns.append(f"{column} = ?")
            params.append(fields[api_key])
    set_columns.append("updated_at = ?")
    params.append(_now())

    conn = get_connection()
    try:
        subnet_row = conn.execute("SELECT id FROM ipam_subnets WHERE id = ?", (subnet_id,)).fetchone()
        if subnet_row is None:
            raise ValueError("Subnet not found")

        placeholders = ",".join("?" for _ in address_ids)
        conn.execute(
            f"""
            UPDATE ipam_addresses
            SET {", ".join(set_columns)}
            WHERE subnet_id = ? AND id IN ({placeholders})
            """,
            (*params, subnet_id, *address_ids),
        )
        conn.commit()
    finally:
        conn.close()
    return get_subnet(subnet_id)


def list_scan_excludes(subnet_id: int) -> List[str]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT address FROM ipam_scan_excludes WHERE subnet_id = ?", (subnet_id,)
        ).fetchall()
        return [row["address"] for row in rows]
    finally:
        conn.close()


def list_scan_excludes_detailed(subnet_id: int) -> List[Dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, address FROM ipam_scan_excludes WHERE subnet_id = ? ORDER BY address",
            (subnet_id,),
        ).fetchall()
        return [{"id": row["id"], "address": row["address"]} for row in rows]
    finally:
        conn.close()


def add_scan_exclude(subnet_id: int, address: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO ipam_scan_excludes (subnet_id, address) VALUES (?, ?)",
            (subnet_id, address),
        )
        conn.commit()
    finally:
        conn.close()


def remove_scan_exclude(subnet_id: int, address: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM ipam_scan_excludes WHERE subnet_id = ? AND address = ?",
            (subnet_id, address),
        )
        conn.commit()
    finally:
        conn.close()


def remove_scan_exclude_by_id(subnet_id: int, exclude_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM ipam_scan_excludes WHERE id = ? AND subnet_id = ?",
            (exclude_id, subnet_id),
        )
        conn.commit()
    finally:
        conn.close()


def apply_scan_result(subnet_id: int, address: str, alive: bool, hostname: Optional[str]) -> None:
    """
    Reconcile one scan_one() result into ipam_addresses.

    Locked rows are never touched. Otherwise: a live address is recorded
    as 'used' (creating the row if needed); a dead address only reverts
    an existing 'used' row back to 'free' — it never touches rows that
    are already 'free' or 'reserved', and never creates a row for an
    address nobody had recorded. This function only ever writes status,
    hostname, and updated_at — team/machine_type/vm_cluster/environment
    are left completely alone.
    """
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT status, locked FROM ipam_addresses WHERE subnet_id = ? AND address = ?",
            (subnet_id, address),
        ).fetchone()

        if existing is not None and existing["locked"]:
            return

        if alive:
            if existing is not None:
                conn.execute(
                    "UPDATE ipam_addresses SET status = ?, hostname = ?, updated_at = ? WHERE subnet_id = ? AND address = ?",
                    ("used", hostname, _now(), subnet_id, address),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO ipam_addresses (subnet_id, address, status, hostname, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (subnet_id, address, "used", hostname, _now()),
                )
        else:
            if existing is not None and existing["status"] == "used":
                conn.execute(
                    "UPDATE ipam_addresses SET status = ?, hostname = NULL, updated_at = ? WHERE subnet_id = ? AND address = ?",
                    ("free", _now(), subnet_id, address),
                )

        conn.commit()
    finally:
        conn.close()


def _scan_dict(row: sqlite3.Row) -> Dict:
    return {
        "id": row["id"],
        "subnet_id": row["subnet_id"],
        "startedAt": row["started_at"],
        "finishedAt": row["finished_at"],
        "scannedCount": row["scanned_count"],
        "usedCount": row["used_count"],
        "freeCount": row["free_count"],
        "skippedCount": row["skipped_count"],
        "newlyUsedCount": row["newly_used_count"],
        "wentQuietCount": row["went_quiet_count"],
        "hostnameChangedCount": row["hostname_changed_count"],
        "diff": json.loads(row["diff_json"]),
    }


def record_scan(
    subnet_id: int,
    started_at: str,
    finished_at: str,
    scanned_count: int,
    used_count: int,
    free_count: int,
    skipped_count: int,
    diff: dict,
) -> Dict:
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO ipam_scans
                (subnet_id, started_at, finished_at, scanned_count, used_count, free_count,
                 skipped_count, newly_used_count, went_quiet_count, hostname_changed_count, diff_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                subnet_id,
                started_at,
                finished_at,
                scanned_count,
                used_count,
                free_count,
                skipped_count,
                len(diff["newlyUsed"]),
                len(diff["wentQuiet"]),
                len(diff["hostnameChanged"]),
                json.dumps(diff),
            ),
        )
        scan_id = cur.lastrowid
        conn.commit()
        row = conn.execute("SELECT * FROM ipam_scans WHERE id = ?", (scan_id,)).fetchone()
        return _scan_dict(row)
    finally:
        conn.close()


def list_scans(subnet_id: int, limit: int = 20) -> List[Dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM ipam_scans WHERE subnet_id = ? ORDER BY started_at DESC, id DESC LIMIT ?",
            (subnet_id, limit),
        ).fetchall()
        return [_scan_dict(row) for row in rows]
    finally:
        conn.close()


def get_last_scan(subnet_id: int) -> Optional[Dict]:
    scans = list_scans(subnet_id, limit=1)
    return scans[0] if scans else None


def get_ipam_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT value FROM ipam_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_ipam_setting(key: str, value: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO ipam_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


SCAN_CONCURRENCY_DEFAULT = 32
SCAN_CONCURRENCY_MIN = 1
SCAN_CONCURRENCY_MAX = 256


def get_scan_concurrency_limit() -> int:
    raw = get_ipam_setting("scan_concurrency_limit", str(SCAN_CONCURRENCY_DEFAULT))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return SCAN_CONCURRENCY_DEFAULT
    if value < SCAN_CONCURRENCY_MIN or value > SCAN_CONCURRENCY_MAX:
        return SCAN_CONCURRENCY_DEFAULT
    return value


def set_scan_concurrency_limit(value: int) -> int:
    if value < SCAN_CONCURRENCY_MIN or value > SCAN_CONCURRENCY_MAX:
        raise ValueError(
            f"Concurrency limit must be between {SCAN_CONCURRENCY_MIN} and {SCAN_CONCURRENCY_MAX}"
        )
    set_ipam_setting("scan_concurrency_limit", str(value))
    return value