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
import re
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

        # DHCP Pools table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ipam_dhcp_pools (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subnet_id INTEGER NOT NULL REFERENCES ipam_subnets(id) ON DELETE CASCADE,
                start_ip TEXT NOT NULL,
                end_ip TEXT NOT NULL,
                name TEXT,
                description TEXT,
                updated_at TEXT NOT NULL,
                manually_placed INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        # Migration: databases created before manual-move tracking existed
        # won't have this column yet — add it in place, same pattern as
        # above. Existing pools default to 0 (not manually placed), so
        # auto-relocation keeps behaving for them exactly as before.
        dhcp_pool_cols = {row["name"] for row in conn.execute("PRAGMA table_info(ipam_dhcp_pools)").fetchall()}
        if "manually_placed" not in dhcp_pool_cols:
            conn.execute("ALTER TABLE ipam_dhcp_pools ADD COLUMN manually_placed INTEGER NOT NULL DEFAULT 0")

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

        # Custom Tags Tables
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ipam_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                color TEXT NOT NULL DEFAULT '#6366f1',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ipam_tag_subnets (
                tag_id INTEGER NOT NULL REFERENCES ipam_tags(id) ON DELETE CASCADE,
                subnet_id INTEGER NOT NULL REFERENCES ipam_subnets(id) ON DELETE CASCADE,
                PRIMARY KEY (tag_id, subnet_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ipam_tag_addresses (
                tag_id INTEGER NOT NULL REFERENCES ipam_tags(id) ON DELETE CASCADE,
                address_id INTEGER NOT NULL REFERENCES ipam_addresses(id) ON DELETE CASCADE,
                PRIMARY KEY (tag_id, address_id)
            )
            """
        )

        # Validation Tables
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS validation_test_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                change_ticket TEXT,
                category TEXT,
                description TEXT,
                target_devices TEXT,
                scenario_modules TEXT,
                config_parameters TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS validation_baselines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER REFERENCES validation_test_plans(id) ON DELETE CASCADE,
                ticket_number TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                captured_by TEXT NOT NULL,
                raw_outputs TEXT,
                parsed_metrics TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS validation_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER REFERENCES validation_test_plans(id) ON DELETE CASCADE,
                baseline_id INTEGER REFERENCES validation_baselines(id),
                run_type TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                executor_username TEXT NOT NULL,
                overall_result TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS validation_test_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER REFERENCES validation_runs(id) ON DELETE CASCADE,
                test_id TEXT NOT NULL,
                layer TEXT,
                target_device TEXT NOT NULL,
                command_executed TEXT NOT NULL,
                raw_output TEXT,
                status TEXT NOT NULL,
                pass_criteria TEXT,
                delta_summary TEXT,
                error_message TEXT,
                executed_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS validation_pir_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER REFERENCES validation_runs(id) ON DELETE CASCADE,
                signoff_user TEXT,
                signoff_status TEXT,
                signoff_notes TEXT,
                generated_at TEXT,
                report_data TEXT
            )
            """
        )

        # Custom Tags Tables
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ipam_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                color TEXT NOT NULL DEFAULT '#6366f1',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ipam_tag_subnets (
                tag_id INTEGER NOT NULL REFERENCES ipam_tags(id) ON DELETE CASCADE,
                subnet_id INTEGER NOT NULL REFERENCES ipam_subnets(id) ON DELETE CASCADE,
                PRIMARY KEY (tag_id, subnet_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ipam_tag_addresses (
                tag_id INTEGER NOT NULL REFERENCES ipam_tags(id) ON DELETE CASCADE,
                address_id INTEGER NOT NULL REFERENCES ipam_addresses(id) ON DELETE CASCADE,
                PRIMARY KEY (tag_id, address_id)
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
    auto_relocate_dhcp_pools(conn)


def find_best_subnet_for_ip_range(start_ip: str, end_ip: str, subnets: List[Dict]) -> Optional[Dict]:
    """
    Given a range [start_ip, end_ip] and a list of subnet dicts, return the subnet dict
    whose CIDR contains both endpoints and has the smallest number of addresses.
    Returns None if no subnet in the list contains the entire range.
    """
    try:
        start_addr = ipaddress.IPv4Address(start_ip.strip())
        end_addr = ipaddress.IPv4Address(end_ip.strip())
    except ValueError:
        return None
    best = None
    best_size = None
    for s in subnets:
        net = ipaddress.IPv4Network(s["cidr"])
        if start_addr in net and end_addr in net:
            if best_size is None or net.num_addresses < best_size:
                best, best_size = s, net.num_addresses
    return best


def auto_relocate_dhcp_pools(conn: sqlite3.Connection) -> None:
    """Re-home DHCP pools into the most specific subnet that contains them.

    Pools the user has explicitly moved (move_dhcp_pool / bulk_move_dhcp_pools)
    are marked manually_placed and skipped here — otherwise a deliberate
    manual move would get silently reverted the next time this runs (e.g.
    on any subsequent subnet create/update/delete), which is confusing:
    the pool appears to "move itself back" for no visible reason.
    """
    rows = conn.execute("SELECT id, cidr FROM ipam_subnets").fetchall()
    if not rows:
        return
    subnets = [{"id": r["id"], "cidr": r["cidr"]} for r in rows]
    pool_rows = conn.execute(
        "SELECT id, subnet_id, start_ip, end_ip FROM ipam_dhcp_pools WHERE manually_placed = 0"
    ).fetchall()
    for p in pool_rows:
        best = find_best_subnet_for_ip_range(p["start_ip"], p["end_ip"], subnets)
        if best and best["id"] != p["subnet_id"]:
            start_int = ip_to_int(p["start_ip"])
            end_int = ip_to_int(p["end_ip"])
            existing_pools = conn.execute(
                "SELECT start_ip, end_ip FROM ipam_dhcp_pools WHERE subnet_id = ? AND id != ?",
                (best["id"], p["id"]),
            ).fetchall()
            overlap = False
            for ep in existing_pools:
                es = ip_to_int(ep["start_ip"])
                ee = ip_to_int(ep["end_ip"])
                if not (end_int < es or start_int > ee):
                    overlap = True
                    break
            if not overlap:
                conn.execute("UPDATE ipam_dhcp_pools SET subnet_id = ? WHERE id = ?", (best["id"], p["id"]))


def find_best_subnet_for_address(address: str, subnets: List[Dict]) -> Optional[Dict]:
    """
    Given an address and a list of subnet dicts (each must have "id" and
    "cidr"), return the subnet dict whose CIDR contains the address and
    has the smallest number of addresses (i.e. the most specific match).
    Returns None if no subnet in the list contains the address.
    """
    ip = ipaddress.ip_address(address.strip())
    best = None
    best_size = None
    for s in subnets:
        net = ipaddress.ip_network(s["cidr"])
        if net.version != ip.version:
            continue
        if ip in net:
            if best_size is None or net.num_addresses < best_size:
                best, best_size = s, net.num_addresses
    return best


def get_next_available_ip(subnet_id: int) -> Optional[str]:
    """
    返回指定subnet中第一个可用的未分配IP地址。
    可用定义：不在 ipam_addresses(status='used'/'reserved') 中，且不在 ipam_scan_excludes 中，
    且不在 ipam_dhcp_pools 的 start_ip~end_ip 范围内。
    遍历 net.hosts()（/31或/32时用net.network_address/net.broadcast_address）。
    全部占满则返回 None。
    """
    conn = get_connection()
    try:
        subnet_row = conn.execute(
            "SELECT cidr FROM ipam_subnets WHERE id = ?", (subnet_id,)
        ).fetchone()
        if subnet_row is None:
            raise ValueError(f"Subnet {subnet_id} not found")
        net = ipaddress.ip_network(subnet_row["cidr"])

        # Collect used IPs (status 'used' or 'reserved')
        used_rows = conn.execute(
            "SELECT address FROM ipam_addresses WHERE subnet_id = ? AND status IN ('used','reserved')",
            (subnet_id,),
        ).fetchall()
        unavailable = {ipaddress.ip_address(r["address"]) for r in used_rows}

        # Collect scan exclude IPs
        exclude_rows = conn.execute(
            "SELECT address FROM ipam_scan_excludes WHERE subnet_id = ?", (subnet_id,)
        ).fetchall()
        for ex in exclude_rows:
            try:
                # The exclude might be a CIDR range; first try to parse as a single IP
                ip = ipaddress.ip_address(ex["address"])
                unavailable.add(ip)
            except ValueError:
                # CIDR format — exclude the entire network
                try:
                    excl_net = ipaddress.ip_network(ex["address"], strict=False)
                    for host in excl_net.hosts():
                        unavailable.add(host)
                except ValueError:
                    pass

        # Collect DHCP pool IPs
        pool_rows = conn.execute(
            "SELECT start_ip, end_ip FROM ipam_dhcp_pools WHERE subnet_id = ?", (subnet_id,)
        ).fetchall()
        for p in pool_rows:
            s = ipaddress.IPv4Address(p["start_ip"])
            e = ipaddress.IPv4Address(p["end_ip"])
            for ip_int in range(int(s), int(e) + 1):
                unavailable.add(ipaddress.IPv4Address(ip_int))

        # Iterate through available IPs
        if net.prefixlen >= 31:
            # /31 or /32: return network address (typically not broadcast)
            candidates = [net.network_address]
            if net.prefixlen == 32:
                candidates = [net.network_address]
        else:
            candidates = list(net.hosts())

        for candidate in candidates:
            if candidate not in unavailable:
                return str(candidate)
        return None
    finally:
        conn.close()


def list_misplaced_addresses() -> List[Dict]:
    """
    Scan every recorded address across every subnet and flag the ones
    that belong in a more specific subnet than the one they're
    currently filed under.
    """
    subnets = list_subnets()
    subnets_by_id = {s["id"]: s for s in subnets}
    misplaced = []
    for subnet in subnets:
        for addr in get_addresses_by_subnet(subnet["id"]):
            best = find_best_subnet_for_address(addr["address"], subnets)
            if best is not None and best["id"] != subnet["id"]:
                misplaced.append({
                    "addressId": addr["id"],
                    "address": addr["address"],
                    "status": addr["status"],
                    "hostname": addr["hostname"],
                    "currentSubnetId": subnet["id"],
                    "currentSubnetCidr": subnet["cidr"],
                    "proposedSubnetId": best["id"],
                    "proposedSubnetCidr": best["cidr"],
                })
    return misplaced


def move_address(from_subnet_id: int, address_id: int, to_subnet_id: int) -> Dict:
    conn = get_connection()
    try:
        from_row = conn.execute(
            "SELECT * FROM ipam_addresses WHERE id = ? AND subnet_id = ?",
            (address_id, from_subnet_id),
        ).fetchone()
        if from_row is None:
            raise ValueError("Address not found in source subnet")
        to_subnet_row = conn.execute(
            "SELECT cidr FROM ipam_subnets WHERE id = ?", (to_subnet_id,)
        ).fetchone()
        if to_subnet_row is None:
            raise ValueError("Destination subnet not found")
        validate_address_in_subnet(from_row["address"], to_subnet_row["cidr"])
        conn.execute(
            "DELETE FROM ipam_addresses WHERE id = ? AND subnet_id = ?",
            (address_id, from_subnet_id),
        )
        try:
            conn.execute(
                """
                INSERT INTO ipam_addresses
                    (subnet_id, address, status, hostname, description, team, machine_type, vm_cluster, environment, locked, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    to_subnet_id, from_row["address"], from_row["status"],
                    from_row["hostname"], from_row["description"], from_row["team"],
                    from_row["machine_type"], from_row["vm_cluster"],
                    from_row["environment"], from_row["locked"], _now(),
                ),
            )
        except sqlite3.IntegrityError:
            raise ValueError(f'"{from_row["address"]}" is already recorded in the destination subnet')
        conn.commit()
    finally:
        conn.close()
    return {"fromSubnet": get_subnet(from_subnet_id), "toSubnet": get_subnet(to_subnet_id)}


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


def search_addresses(query: str, limit: int = 50) -> List[Dict]:
    if not query or not query.strip():
        return []
    stripped_q = query.strip()
    q = f"%{stripped_q}%"
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT a.*, s.cidr AS subnet_cidr, s.vlan AS subnet_vlan
            FROM ipam_addresses a
            JOIN ipam_subnets s ON a.subnet_id = s.id
            WHERE a.hostname LIKE ? 
               OR a.address LIKE ? 
               OR a.description LIKE ?
               OR a.team LIKE ?
               OR a.vm_cluster LIKE ?
            ORDER BY
                CASE WHEN LOWER(a.hostname) = LOWER(?) THEN 0 
                     WHEN a.hostname LIKE ? THEN 1 
                     ELSE 2 END,
                a.hostname ASC,
                a.address ASC
            LIMIT ?
            """,
            (q, q, q, q, q, stripped_q, q, limit),
        ).fetchall()
        results = []
        for r in rows:
            d = _address_dict(r)
            d["subnetId"] = r["subnet_id"]
            d["subnetCidr"] = r["subnet_cidr"]
            d["subnetVlan"] = r["subnet_vlan"]
            results.append(d)
        return results
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

        pool_rows = conn.execute(
            "SELECT start_ip, end_ip FROM ipam_dhcp_pools WHERE subnet_id = ?", (subnet_id,)
        ).fetchall()
        outside_pools = [
            f"{r['start_ip']}-{r['end_ip']}" for r in pool_rows
            if ipaddress.IPv4Address(r["start_ip"]) not in network or ipaddress.IPv4Address(r["end_ip"]) not in network
        ]
        if outside_pools:
            raise ValueError(
                f"Can't resize to {cidr} — DHCP pool(s) would fall outside it ({outside_pools[0]}). Delete or move them first."
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


def bulk_delete_addresses(subnet_id: int, address_ids: List[int]) -> Dict:
    """
    Delete many addresses within one subnet in a single transaction.

    address_ids not belonging to subnet_id are silently skipped (the
    WHERE clause simply won't match them) rather than raising, matching
    the behavior of bulk_update_addresses.
    """
    conn = get_connection()
    try:
        subnet_row = conn.execute("SELECT id FROM ipam_subnets WHERE id = ?", (subnet_id,)).fetchone()
        if subnet_row is None:
            raise ValueError("Subnet not found")

        placeholders = ",".join("?" for _ in address_ids)
        conn.execute(
            f"DELETE FROM ipam_addresses WHERE subnet_id = ? AND id IN ({placeholders})",
            (subnet_id, *address_ids),
        )
        conn.commit()
    finally:
        conn.close()
    return get_subnet(subnet_id)


def bulk_move_addresses(from_subnet_id: int, address_ids: List[int], to_subnet_id: int) -> Dict:
    """
    Move many addresses from one subnet to another in a single transaction.

    Each address is checked independently: address_ids not belonging to
    from_subnet_id are silently skipped (same convention as
    bulk_update_addresses/bulk_delete_addresses); addresses that don't fit
    the destination CIDR, or that collide with an address already recorded
    there, are recorded in `skipped` with a reason and left in place rather
    than aborting the whole batch.
    """
    conn = get_connection()
    try:
        from_subnet_row = conn.execute(
            "SELECT id FROM ipam_subnets WHERE id = ?", (from_subnet_id,)
        ).fetchone()
        if from_subnet_row is None:
            raise ValueError("Source subnet not found")
        to_subnet_row = conn.execute(
            "SELECT cidr FROM ipam_subnets WHERE id = ?", (to_subnet_id,)
        ).fetchone()
        if to_subnet_row is None:
            raise ValueError("Destination subnet not found")
        if to_subnet_id == from_subnet_id:
            raise ValueError("Source and destination subnet must be different")

        target_cidr = to_subnet_row["cidr"]
        moved_count = 0
        skipped: List[Dict] = []

        for address_id in address_ids:
            row = conn.execute(
                "SELECT * FROM ipam_addresses WHERE id = ? AND subnet_id = ?",
                (address_id, from_subnet_id),
            ).fetchone()
            if row is None:
                continue

            try:
                validate_address_in_subnet(row["address"], target_cidr)
            except ValueError as exc:
                skipped.append({"addressId": address_id, "address": row["address"], "reason": str(exc)})
                continue

            exists = conn.execute(
                "SELECT 1 FROM ipam_addresses WHERE subnet_id = ? AND address = ?",
                (to_subnet_id, row["address"]),
            ).fetchone()
            if exists:
                skipped.append({
                    "addressId": address_id,
                    "address": row["address"],
                    "reason": f'"{row["address"]}" is already recorded in the destination subnet',
                })
                continue

            conn.execute(
                "DELETE FROM ipam_addresses WHERE id = ? AND subnet_id = ?",
                (address_id, from_subnet_id),
            )
            conn.execute(
                """
                INSERT INTO ipam_addresses
                    (subnet_id, address, status, hostname, description, team, machine_type, vm_cluster, environment, locked, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    to_subnet_id, row["address"], row["status"],
                    row["hostname"], row["description"], row["team"],
                    row["machine_type"], row["vm_cluster"],
                    row["environment"], row["locked"], _now(),
                ),
            )
            moved_count += 1

        conn.commit()
    finally:
        conn.close()

    return {
        "fromSubnet": get_subnet(from_subnet_id),
        "toSubnet": get_subnet(to_subnet_id),
        "movedCount": moved_count,
        "skipped": skipped,
    }


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
    as 'used' (creating the row if needed, unless a more specific subnet
    already has a row for that same address — see below); a dead address
    only reverts an existing 'used' row back to 'free' — it never touches
    rows that are already 'free' or 'reserved', and never creates a row
    for an address nobody had recorded. This function only ever writes
    status, hostname, and updated_at — team/machine_type/vm_cluster/
    environment are left completely alone.

    Creating a new row is skipped when a strictly more specific subnet
    already has this address recorded (e.g. it was moved there via
    resubnet review) — otherwise rescanning the broader subnet would keep
    re-creating a duplicate that resubnet review can never successfully
    move, since the destination already holds it.
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
                # Before creating a fresh row here, check whether some
                # *other* subnet already has this exact address recorded.
                # CIDR blocks in this app are always either disjoint or
                # fully nested (see recompute_subnet_hierarchy), so any
                # other subnet that also contains this address is either
                # an ancestor or a descendant of the one being scanned
                # right now. If a more specific (smaller) one already
                # owns it, don't recreate a duplicate here — this is
                # exactly what used to happen when a host was moved into
                # a narrower subnet via resubnet review and its old,
                # broader subnet got rescanned afterward: the broad scan
                # would just re-insert the address it no longer owns,
                # producing a duplicate that couldn't be re-moved because
                # the destination already held it.
                this_row = conn.execute(
                    "SELECT cidr FROM ipam_subnets WHERE id = ?", (subnet_id,)
                ).fetchone()
                this_size = ipaddress.ip_network(this_row["cidr"]).num_addresses if this_row else None
                owned_elsewhere = conn.execute(
                    """
                    SELECT s.cidr FROM ipam_addresses a
                    JOIN ipam_subnets s ON s.id = a.subnet_id
                    WHERE a.address = ? AND a.subnet_id != ?
                    """,
                    (address, subnet_id),
                ).fetchall()
                more_specific_owner_exists = this_size is not None and any(
                    ipaddress.ip_network(row["cidr"]).num_addresses < this_size
                    for row in owned_elsewhere
                )
                if more_specific_owner_exists:
                    return
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


def ip_to_int(ip_str: str) -> int:
    return int(ipaddress.IPv4Address(ip_str))


def int_to_ip(ip_int: int) -> str:
    return str(ipaddress.IPv4Address(ip_int))


def add_dhcp_pool(
    subnet_id: int,
    start_ip: str,
    end_ip: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict:
    try:
        start_addr = ipaddress.IPv4Address(start_ip)
        end_addr = ipaddress.IPv4Address(end_ip)
    except ipaddress.AddressValueError as e:
        raise ValueError(f"Invalid IP address: {e}")

    if start_addr > end_addr:
        raise ValueError("start_ip must be less than or equal to end_ip")

    conn = get_connection()
    try:
        subnet_row = conn.execute(
            "SELECT cidr FROM ipam_subnets WHERE id = ?", (subnet_id,)
        ).fetchone()
        if not subnet_row:
            raise ValueError(f"Subnet {subnet_id} not found")

        subnet_net = ipaddress.IPv4Network(subnet_row["cidr"])
        if start_addr not in subnet_net or end_addr not in subnet_net:
            raise ValueError(
                f"IP range {start_ip}-{end_ip} is not within subnet {subnet_row['cidr']}"
            )

        start_int = ip_to_int(start_ip)
        end_int = ip_to_int(end_ip)

        existing_pools = conn.execute(
            "SELECT start_ip, end_ip FROM ipam_dhcp_pools WHERE subnet_id = ?",
            (subnet_id,),
        ).fetchall()

        for pool in existing_pools:
            existing_start = ip_to_int(pool["start_ip"])
            existing_end = ip_to_int(pool["end_ip"])

            if not (end_int < existing_start or start_int > existing_end):
                raise ValueError(
                    f"DHCP pool range overlaps with existing pool {pool['start_ip']}-{pool['end_ip']}"
                )

        updated_at = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            """
            INSERT INTO ipam_dhcp_pools
                (subnet_id, start_ip, end_ip, name, description, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (subnet_id, start_ip, end_ip, name, description, updated_at),
        )
        pool_id = cur.lastrowid
        # Re-check hierarchy now that the pool exists — if a more-specific
        # subnet fully contains this range, auto-relocate into it.
        auto_relocate_dhcp_pools(conn)
        conn.commit()

        row = conn.execute(
            "SELECT * FROM ipam_dhcp_pools WHERE id = ?", (pool_id,)
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_dhcp_pools(subnet_id: int) -> List[Dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM ipam_dhcp_pools WHERE subnet_id = ? ORDER BY start_ip",
            (subnet_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def delete_dhcp_pool(pool_id: int) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM ipam_dhcp_pools WHERE id = ?", (pool_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def update_dhcp_pool(
    pool_id: int,
    start_ip: str,
    end_ip: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict:
    try:
        start_addr = ipaddress.IPv4Address(start_ip)
        end_addr = ipaddress.IPv4Address(end_ip)
    except ipaddress.AddressValueError as e:
        raise ValueError(f"Invalid IP address: {e}")

    if start_addr > end_addr:
        raise ValueError("start_ip must be less than or equal to end_ip")

    conn = get_connection()
    try:
        pool_row = conn.execute(
            "SELECT * FROM ipam_dhcp_pools WHERE id = ?", (pool_id,)
        ).fetchone()
        if pool_row is None:
            raise ValueError("DHCP pool not found")

        subnet_row = conn.execute(
            "SELECT cidr FROM ipam_subnets WHERE id = ?", (pool_row["subnet_id"],)
        ).fetchone()
        subnet_net = ipaddress.IPv4Network(subnet_row["cidr"])
        if start_addr not in subnet_net or end_addr not in subnet_net:
            raise ValueError(
                f"IP range {start_ip}-{end_ip} is not within subnet {subnet_row['cidr']}"
            )

        start_int = ip_to_int(start_ip)
        end_int = ip_to_int(end_ip)

        # Check overlap with OTHER pools in the same subnet (exclude self)
        existing_pools = conn.execute(
            "SELECT start_ip, end_ip FROM ipam_dhcp_pools WHERE subnet_id = ? AND id != ?",
            (pool_row["subnet_id"], pool_id),
        ).fetchall()
        for p in existing_pools:
            es = ip_to_int(p["start_ip"])
            ee = ip_to_int(p["end_ip"])
            if not (end_int < es or start_int > ee):
                raise ValueError(
                    f"DHCP pool range overlaps with existing pool {p['start_ip']}-{p['end_ip']}"
                )

        updated_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            UPDATE ipam_dhcp_pools
            SET start_ip = ?, end_ip = ?, name = ?, description = ?, updated_at = ?
            WHERE id = ?
            """,
            (start_ip, end_ip, name, description, updated_at, pool_id),
        )
        conn.commit()
        updated_row = conn.execute(
            "SELECT * FROM ipam_dhcp_pools WHERE id = ?", (pool_id,)
        ).fetchone()
        return dict(updated_row)
    finally:
        conn.close()


def bulk_move_dhcp_pools(pool_ids: List[int], to_subnet_id: int) -> Dict:
    if not pool_ids:
        raise ValueError("No pools selected")
    conn = get_connection()
    try:
        to_subnet_row = conn.execute(
            "SELECT cidr FROM ipam_subnets WHERE id = ?", (to_subnet_id,)
        ).fetchone()
        if to_subnet_row is None:
            raise ValueError("Destination subnet not found")
        to_net = ipaddress.IPv4Network(to_subnet_row["cidr"])

        skipped = []
        moved_count = 0
        pool_rows = conn.execute(
            "SELECT * FROM ipam_dhcp_pools WHERE id IN ({})".format(
                ",".join("?" * len(pool_ids))
            ),
            pool_ids,
        ).fetchall()

        for p in pool_rows:
            start_addr = ipaddress.IPv4Address(p["start_ip"])
            end_addr = ipaddress.IPv4Address(p["end_ip"])
            if start_addr not in to_net or end_addr not in to_net:
                skipped.append({
                    "poolId": p["id"],
                    "startIp": p["start_ip"],
                    "endIp": p["end_ip"],
                    "reason": f"Range not within subnet {to_subnet_row['cidr']}",
                })
                continue

            start_int = ip_to_int(p["start_ip"])
            end_int = ip_to_int(p["end_ip"])
            existing_in_target = conn.execute(
                "SELECT start_ip, end_ip FROM ipam_dhcp_pools WHERE subnet_id = ? AND id != ?",
                (to_subnet_id, p["id"]),
            ).fetchall()
            overlap = False
            for ep in existing_in_target:
                es = ip_to_int(ep["start_ip"])
                ee = ip_to_int(ep["end_ip"])
                if not (end_int < es or start_int > ee):
                    overlap = True
                    break
            if overlap:
                skipped.append({
                    "poolId": p["id"],
                    "startIp": p["start_ip"],
                    "endIp": p["end_ip"],
                    "reason": "Overlaps with existing pool in destination subnet",
                })
                continue

            conn.execute(
                "UPDATE ipam_dhcp_pools SET subnet_id = ?, manually_placed = 1 WHERE id = ?",
                (to_subnet_id, p["id"]),
            )
            moved_count += 1

        conn.commit()
        return {
            "movedCount": moved_count,
            "skipped": skipped,
            "fromSubnet": None,
            "toSubnet": get_subnet(to_subnet_id),
        }
    finally:
        conn.close()


def check_ip_in_dhcp_pool(ip_address: str, subnet_id: int) -> bool:
    try:
        ip_addr = ipaddress.IPv4Address(ip_address)
    except ipaddress.AddressValueError:
        return False

    ip_int = ip_to_int(ip_address)

    conn = get_connection()
    try:
        pools = conn.execute(
            "SELECT start_ip, end_ip FROM ipam_dhcp_pools WHERE subnet_id = ?",
            (subnet_id,),
        ).fetchall()

        for pool in pools:
            start_int = ip_to_int(pool["start_ip"])
            end_int = ip_to_int(pool["end_ip"])
            if start_int <= ip_int <= end_int:
                return True

        return False
    finally:
        conn.close()


def get_dhcp_pool_by_id(pool_id: int) -> Optional[Dict]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM ipam_dhcp_pools WHERE id = ?", (pool_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_misplaced_dhcp_pools() -> List[Dict]:
    subnets = list_subnets()
    misplaced = []
    conn = get_connection()
    try:
        pool_rows = conn.execute(
            """
            SELECT p.*, s.cidr AS current_cidr
            FROM ipam_dhcp_pools p
            JOIN ipam_subnets s ON p.subnet_id = s.id
            WHERE p.manually_placed = 0
            """
        ).fetchall()
        for p in pool_rows:
            best = find_best_subnet_for_ip_range(p["start_ip"], p["end_ip"], subnets)
            if best is not None and best["id"] != p["subnet_id"]:
                misplaced.append({
                    "poolId": p["id"],
                    "startIp": p["start_ip"],
                    "endIp": p["end_ip"],
                    "name": p["name"],
                    "description": p["description"],
                    "currentSubnetId": p["subnet_id"],
                    "currentSubnetCidr": p["current_cidr"],
                    "proposedSubnetId": best["id"],
                    "proposedSubnetCidr": best["cidr"],
                })
        return misplaced
    finally:
        conn.close()


def move_dhcp_pool(from_subnet_id: int, pool_id: int, to_subnet_id: int) -> Dict:
    conn = get_connection()
    try:
        pool_row = conn.execute(
            "SELECT * FROM ipam_dhcp_pools WHERE id = ? AND subnet_id = ?",
            (pool_id, from_subnet_id),
        ).fetchone()
        if pool_row is None:
            raise ValueError("DHCP pool not found in source subnet")
        to_subnet_row = conn.execute(
            "SELECT cidr FROM ipam_subnets WHERE id = ?", (to_subnet_id,)
        ).fetchone()
        if to_subnet_row is None:
            raise ValueError("Destination subnet not found")

        start_addr = ipaddress.IPv4Address(pool_row["start_ip"])
        end_addr = ipaddress.IPv4Address(pool_row["end_ip"])
        to_net = ipaddress.IPv4Network(to_subnet_row["cidr"])
        if start_addr not in to_net or end_addr not in to_net:
            raise ValueError(
                f"DHCP pool range {pool_row['start_ip']}-{pool_row['end_ip']} is not within subnet {to_subnet_row['cidr']}"
            )

        start_int = ip_to_int(pool_row["start_ip"])
        end_int = ip_to_int(pool_row["end_ip"])
        existing_pools = conn.execute(
            "SELECT start_ip, end_ip FROM ipam_dhcp_pools WHERE subnet_id = ? AND id != ?",
            (to_subnet_id, pool_id),
        ).fetchall()

        for p in existing_pools:
            es = ip_to_int(p["start_ip"])
            ee = ip_to_int(p["end_ip"])
            if not (end_int < es or start_int > ee):
                raise ValueError(
                    f"DHCP pool range overlaps with existing pool in destination subnet: {p['start_ip']}-{p['end_ip']}"
                )

        conn.execute(
            "UPDATE ipam_dhcp_pools SET subnet_id = ?, manually_placed = 1 WHERE id = ?",
            (to_subnet_id, pool_id),
        )
        conn.commit()
        return {"fromSubnet": get_subnet(from_subnet_id), "toSubnet": get_subnet(to_subnet_id)}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Custom Tags
# ---------------------------------------------------------------------------

_TAG_NAME_RE = re.compile(r'^[a-zA-Z0-9_-]{2,50}$')


def _validate_tag_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise ValueError("Tag name is required")
    if len(name) > 50:
        raise ValueError("Tag name must be at most 50 characters")
    if not _TAG_NAME_RE.match(name):
        raise ValueError("Tag name must be 2-50 characters, alphanumeric, hyphens, and underscores only")
    return name


def _validate_tag_color(color: str) -> str:
    color = color.strip()
    if not color:
        return "#6366f1"
    if not re.match(r'^#[0-9a-fA-F]{6}$', color):
        raise ValueError("Tag color must be a hex value (e.g. #6366f1)")
    return color


def create_tag(name: str, description: Optional[str] = None, color: Optional[str] = None) -> Dict:
    name = _validate_tag_name(name)
    if description is not None:
        description = description.strip()
        if len(description) > 200:
            raise ValueError("Tag description must be at most 200 characters")
    color = _validate_tag_color(color or "#6366f1")

    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO ipam_tags (name, description, color, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, description, color, _now(), _now()),
        )
        conn.commit()
        tag_id = cur.lastrowid
        return get_tag(tag_id)
    finally:
        conn.close()


def get_tag(tag_id: int) -> Optional[Dict]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM ipam_tags WHERE id = ?", (tag_id,)).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "color": row["color"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
    finally:
        conn.close()


def get_tags() -> List[Dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM ipam_tags ORDER BY name COLLATE NOCASE").fetchall()
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "color": row["color"],
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
            }
            for row in rows
        ]
    finally:
        conn.close()


def delete_tag(tag_id: int) -> bool:
    conn = get_connection()
    try:
        tag = conn.execute("SELECT id FROM ipam_tags WHERE id = ?", (tag_id,)).fetchone()
        if tag is None:
            return False
        conn.execute("DELETE FROM ipam_tags WHERE id = ?", (tag_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def add_subnet_tag(subnet_id: int, tag_id: int) -> None:
    conn = get_connection()
    try:
        subnet = conn.execute("SELECT id FROM ipam_subnets WHERE id = ?", (subnet_id,)).fetchone()
        if subnet is None:
            raise ValueError(f"Subnet {subnet_id} not found")
        tag = conn.execute("SELECT id FROM ipam_tags WHERE id = ?", (tag_id,)).fetchone()
        if tag is None:
            raise ValueError(f"Tag {tag_id} not found")
        conn.execute(
            "INSERT OR IGNORE INTO ipam_tag_subnets (tag_id, subnet_id) VALUES (?, ?)",
            (tag_id, subnet_id),
        )
        conn.commit()
    finally:
        conn.close()


def remove_subnet_tag(subnet_id: int, tag_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM ipam_tag_subnets WHERE tag_id = ? AND subnet_id = ?",
            (tag_id, subnet_id),
        )
        conn.commit()
    finally:
        conn.close()


def add_address_tag(address_id: int, tag_id: int) -> None:
    conn = get_connection()
    try:
        addr = conn.execute("SELECT id FROM ipam_addresses WHERE id = ?", (address_id,)).fetchone()
        if addr is None:
            raise ValueError(f"Address {address_id} not found")
        tag = conn.execute("SELECT id FROM ipam_tags WHERE id = ?", (tag_id,)).fetchone()
        if tag is None:
            raise ValueError(f"Tag {tag_id} not found")
        conn.execute(
            "INSERT OR IGNORE INTO ipam_tag_addresses (tag_id, address_id) VALUES (?, ?)",
            (tag_id, address_id),
        )
        conn.commit()
    finally:
        conn.close()


def remove_address_tag(address_id: int, tag_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM ipam_tag_addresses WHERE tag_id = ? AND address_id = ?",
            (tag_id, address_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_subnets_by_tag(tag_id: int) -> List[Dict]:
    conn = get_connection()
    try:
        tag = conn.execute("SELECT id FROM ipam_tags WHERE id = ?", (tag_id,)).fetchone()
        if tag is None:
            raise ValueError(f"Tag {tag_id} not found")
        rows = conn.execute(
            """
            SELECT s.id, s.cidr, s.vlan, s.description, s.updated_at
            FROM ipam_subnets s
            JOIN ipam_tag_subnets t ON s.id = t.subnet_id
            WHERE t.tag_id = ?
            ORDER BY s.cidr
            """,
            (tag_id,),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "cidr": r["cidr"],
                "vlan": r["vlan"],
                "description": r["description"],
                "updatedAt": r["updated_at"],
                "totalAddresses": 0,
                "usedCount": 0,
                "freeCount": 0,
                "reservedCount": 0,
                "recordedCount": 0,
            }
            for r in rows
        ]
    finally:
        conn.close()


def get_addresses_by_tag(tag_id: int) -> List[Dict]:
    conn = get_connection()
    try:
        tag = conn.execute("SELECT id FROM ipam_tags WHERE id = ?", (tag_id,)).fetchone()
        if tag is None:
            raise ValueError(f"Tag {tag_id} not found")
        rows = conn.execute(
            """
            SELECT a.id, a.address, a.status, a.hostname, a.description,
                   s.id AS subnet_id, s.cidr AS subnet_cidr, s.vlan AS subnet_vlan
            FROM ipam_addresses a
            JOIN ipam_tag_addresses ta ON a.id = ta.address_id
            JOIN ipam_subnets s ON a.subnet_id = s.id
            WHERE ta.tag_id = ?
            ORDER BY s.cidr, a.address
            """,
            (tag_id,),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "address": r["address"],
                "status": r["status"],
                "hostname": r["hostname"],
                "description": r["description"],
                "subnetId": r["subnet_id"],
                "subnetCidr": r["subnet_cidr"],
                "subnetVlan": r["subnet_vlan"],
                "locked": False,
                "updatedAt": _now(),
            }
            for r in rows
        ]
    finally:
        conn.close()


def get_subnet_tags(subnet_id: int) -> List[Dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT t.id, t.name, t.description, t.color
            FROM ipam_tags t
            JOIN ipam_tag_subnets ts ON t.id = ts.tag_id
            WHERE ts.subnet_id = ?
            ORDER BY t.name COLLATE NOCASE
            """,
            (subnet_id,),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "description": r["description"],
                "color": r["color"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def get_address_tags(address_id: int) -> List[Dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT t.id, t.name, t.description, t.color
            FROM ipam_tags t
            JOIN ipam_tag_addresses ta ON t.id = ta.tag_id
            WHERE ta.address_id = ?
            ORDER BY t.name COLLATE NOCASE
            """,
            (address_id,),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "description": r["description"],
                "color": r["color"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def search_tags(query: str) -> List[Dict]:
    conn = get_connection()
    try:
        pattern = f"%{query}%"
        rows = conn.execute(
            "SELECT * FROM ipam_tags WHERE name LIKE ? OR description LIKE ? ORDER BY name COLLATE NOCASE LIMIT 20",
            (pattern, pattern),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "description": r["description"],
                "color": r["color"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def find_next_contiguous_subnet(parent_cidr: str, required_prefix: int) -> Optional[Dict]:
    """
    Find the next available contiguous subnet within a parent CIDR block.
    
    Args:
        parent_cidr: Parent subnet CIDR (e.g., "10.100.0.0/16")
        required_prefix: Required prefix length (e.g., 28)
    
    Returns:
        Dict with recommendation details or None if no space available
    """
    import ipaddress
    
    try:
        parent_net = ipaddress.ip_network(parent_cidr, strict=False)
    except ValueError as e:
        raise ValueError(f"Invalid parent CIDR: {parent_cidr}")
    
    # Validate required prefix
    if required_prefix < parent_net.prefixlen:
        raise ValueError(f"Requested prefix {required_prefix} is larger than parent prefix {parent_net.prefixlen}")
    
    if required_prefix > 32:
        raise ValueError(f"Invalid prefix length: {required_prefix}")
    
    conn = get_connection()
    try:
        # Get all existing subnets that overlap with the parent
        rows = conn.execute("SELECT cidr FROM ipam_subnets").fetchall()
        existing_nets = []
        for r in rows:
            try:
                net = ipaddress.ip_network(r["cidr"])
                # Skip the parent itself and check overlap
                if net == parent_net:
                    continue
                if parent_net.overlaps(net):
                    existing_nets.append(net)
            except ValueError:
                # Skip invalid CIDRs
                continue
        
        # Get all addresses from subnets that overlap with the parent
        # We need to find the subnet IDs first
        subnet_ids = []
        for net in existing_nets:
            # Find subnet ID for this network
            id_row = conn.execute(
                "SELECT id FROM ipam_subnets WHERE cidr = ?",
                (str(net),)
            ).fetchone()
            if id_row:
                subnet_ids.append(id_row["id"])
        
        # Also check the parent subnet itself for addresses
        parent_id_row = conn.execute(
            "SELECT id FROM ipam_subnets WHERE cidr = ?",
            (str(parent_net),)
        ).fetchone()
        if parent_id_row:
            subnet_ids.append(parent_id_row["id"])
        
        # Get all addresses in these subnets
        occupied_ranges = []
        if subnet_ids:
            placeholders = ",".join("?" * len(subnet_ids))
            addr_rows = conn.execute(
                f"SELECT address FROM ipam_addresses WHERE subnet_id IN ({placeholders})",
                subnet_ids
            ).fetchall()
            
            for addr_row in addr_rows:
                try:
                    addr = ipaddress.ip_address(addr_row["address"])
                    if parent_net.network_address <= addr <= parent_net.broadcast_address:
                        # This address is within our parent, treat as occupied
                        occupied_ranges.append((int(addr), int(addr)))
                except ValueError:
                    continue
        
        # Merge overlapping occupied ranges
        occupied_ranges.sort()
        merged_occupied = []
        for start, end in occupied_ranges:
            if merged_occupied and start <= merged_occupied[-1][1] + 1:
                # Overlapping or adjacent, merge
                merged_occupied[-1] = (merged_occupied[-1][0], max(merged_occupied[-1][1], end))
            else:
                merged_occupied.append((start, end))
        
        # Combine existing subnets and occupied addresses into a unified list of blocks to skip
        blocked_ranges = []
        
        # Add existing subnets as blocked ranges
        for net in existing_nets:
            blocked_ranges.append((int(net.network_address), int(net.broadcast_address)))
        
        # Add occupied addresses as blocked ranges
        for start, end in merged_occupied:
            # Only add if not already covered by an existing subnet
            covered = False
            for bs, be in blocked_ranges:
                if bs <= start and be >= end:
                    covered = True
                    break
            if not covered:
                blocked_ranges.append((start, end))
        
        # Sort all blocked ranges
        blocked_ranges.sort()
        
        # Find gaps
        current = int(parent_net.network_address)
        required_size = 2 ** (32 - required_prefix)
        prefix_bits = 32 - required_prefix
        
        for block_start, block_end in blocked_ranges:
            # Skip blocks that are at or after our parent
            if block_start > int(parent_net.broadcast_address):
                break
            
            # Consider the gap before this block
            if block_start > current:
                gap_size = block_start - current
                
                if gap_size >= required_size:
                    # Try to find an aligned subnet in this gap
                    aligned_start = current
                    offset = current & ((1 << prefix_bits) - 1)
                    if offset != 0:
                        aligned_start = current + (required_size - offset)
                    
                    # Check if aligned subnet fits in the gap
                    if aligned_start + required_size <= block_start:
                        # Verify no occupied addresses fall within this subnet
                        subnet_start = aligned_start
                        subnet_end = aligned_start + required_size - 1
                        
                        # Check if any occupied range overlaps with this subnet
                        has_occupation = False
                        for occ_start, occ_end in merged_occupied:
                            if occ_start <= subnet_end and occ_end >= subnet_start:
                                has_occupation = True
                                break
                        
                        if not has_occupation:
                            recommended_net = ipaddress.ip_network(
                                f"{ipaddress.ip_address(aligned_start)}/{required_prefix}",
                                strict=False
                            )
                            
                            return {
                                "parent": str(parent_net),
                                "requestedPrefix": required_prefix,
                                "recommendation": str(recommended_net),
                                "availableFrom": str(recommended_net.network_address),
                                "availableTo": str(recommended_net.broadcast_address),
                                "totalAddresses": recommended_net.num_addresses,
                                "nextAvailableAfter": datetime.utcnow().isoformat() + "Z"
                            }
            
            # Move current past this block
            current = max(current, block_end + 1)
        
        # Check remaining space after last block
        remaining_size = int(parent_net.broadcast_address) - current + 1
        
        if remaining_size >= required_size:
            # Align to prefix boundary
            aligned_start = current
            offset = current & ((1 << prefix_bits) - 1)
            if offset != 0:
                aligned_start = current + (required_size - offset)
            
            if aligned_start + required_size <= int(parent_net.broadcast_address) + 1:
                # Verify no occupied addresses
                subnet_start = aligned_start
                subnet_end = aligned_start + required_size - 1
                
                has_occupation = False
                for occ_start, occ_end in merged_occupied:
                    if occ_start <= subnet_end and occ_end >= subnet_start:
                        has_occupation = True
                        break
                
                if not has_occupation:
                    recommended_net = ipaddress.ip_network(
                        f"{ipaddress.ip_address(aligned_start)}/{required_prefix}",
                        strict=False
                    )
                    
                    return {
                        "parent": str(parent_net),
                        "requestedPrefix": required_prefix,
                        "recommendation": str(recommended_net),
                        "availableFrom": str(recommended_net.network_address),
                        "availableTo": str(recommended_net.broadcast_address),
                        "totalAddresses": recommended_net.num_addresses,
                        "nextAvailableAfter": datetime.utcnow().isoformat() + "Z"
                    }
        
        # No space available
        return {
            "parent": str(parent_net),
            "requestedPrefix": required_prefix,
            "recommendation": None,
            "availableFrom": None,
            "availableTo": None,
            "totalAddresses": 0,
            "nextAvailableAfter": None
        }
    
    finally:
        conn.close()