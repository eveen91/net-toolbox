import hashlib
import ipaddress
import json
import sqlite3
import uuid

import auth_db
from tenancy.transfer import attached_transaction, TransferConflict, HostNotFound


CHILD_TABLES = (
    "ipam_addresses", "ipam_dhcp_pools", "ipam_range_reservations",
    "ipam_scan_excludes", "ipam_scans", "ipam_scan_jobs", "ipam_scan_schedules",
)


def snapshot(conn, subnet_id):
    all_subnets = [dict(r) for r in conn.execute("SELECT * FROM origin.ipam_subnets ORDER BY id")]
    root = next((r for r in all_subnets if r["id"] == subnet_id), None)
    if root is None:
        raise HostNotFound()
    network = ipaddress.ip_network(root["cidr"])
    subnets = [r for r in all_subnets if ipaddress.ip_network(r["cidr"]).subnet_of(network)]
    subnets.sort(key=lambda r: (ipaddress.ip_network(r["cidr"]).prefixlen, r["id"]))
    conn.execute("CREATE TEMP TABLE moving_subnets(id INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO moving_subnets VALUES (?)", [(r["id"],) for r in subnets])
    data = {"ipam_subnets": subnets}
    for table in CHILD_TABLES:
        data[table] = [dict(r) for r in conn.execute(f"SELECT * FROM origin.{table} WHERE subnet_id IN (SELECT id FROM moving_subnets) ORDER BY {('subnet_id' if table == 'ipam_scan_schedules' else 'id')}")]
    # A parent scan can also touch this range. Do not move while any overlapping scan runs.
    running = {r[0] for r in conn.execute("SELECT subnet_id FROM origin.ipam_scan_jobs WHERE status = 'running'")}
    if any(r["id"] in running and ipaddress.ip_network(r["cidr"]).overlaps(network) for r in all_subnets):
        raise TransferConflict("An overlapping subnet has an active scan. Finish or cancel it before moving")
    for row in conn.execute("SELECT cidr FROM destination.ipam_subnets"):
        if ipaddress.ip_network(row["cidr"]).overlaps(network):
            raise TransferConflict(f"Destination subnet {row['cidr']} overlaps the moved network")
    for row in conn.execute("SELECT a.address FROM destination.ipam_addresses a"):
        if ipaddress.ip_address(row["address"]) in network:
            raise TransferConflict("Destination already contains an address in the moved network")
    data["ipam_tag_subnets"] = [dict(r) for r in conn.execute("SELECT * FROM origin.ipam_tag_subnets WHERE subnet_id IN (SELECT id FROM moving_subnets) ORDER BY subnet_id, tag_id")]
    data["ipam_tag_addresses"] = [dict(r) for r in conn.execute("SELECT * FROM origin.ipam_tag_addresses WHERE address_id IN (SELECT id FROM origin.ipam_addresses WHERE subnet_id IN (SELECT id FROM moving_subnets)) ORDER BY address_id, tag_id")]
    data["ipam_tags"] = [dict(r) for r in conn.execute("SELECT * FROM origin.ipam_tags WHERE id IN (SELECT tag_id FROM origin.ipam_tag_subnets WHERE subnet_id IN (SELECT id FROM moving_subnets) UNION SELECT tag_id FROM origin.ipam_tag_addresses WHERE address_id IN (SELECT id FROM origin.ipam_addresses WHERE subnet_id IN (SELECT id FROM moving_subnets))) ORDER BY id")]
    for tag in data["ipam_tags"]:
        existing = conn.execute("SELECT color, description FROM destination.ipam_tags WHERE name = ?", (tag["name"],)).fetchone()
        if existing and (existing["color"], existing["description"]) != (tag["color"], tag["description"]):
            raise TransferConflict(f"Destination tag '{tag['name']}' has different metadata")
    data["ipam_audit_log"] = [dict(r) for r in conn.execute("SELECT * FROM origin.ipam_audit_log WHERE subnet_id IN (SELECT id FROM moving_subnets) OR subnet_cidr IN (SELECT cidr FROM origin.ipam_subnets WHERE id IN (SELECT id FROM moving_subnets)) OR address_id IN (SELECT id FROM origin.ipam_addresses WHERE subnet_id IN (SELECT id FROM moving_subnets)) OR dhcp_pool_id IN (SELECT id FROM origin.ipam_dhcp_pools WHERE subnet_id IN (SELECT id FROM moving_subnets)) ORDER BY id")]
    version = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    return root, data, version


def insert(conn, table, row):
    # Table/column names come solely from module constants and database schemas.
    columns = list(row)
    cursor = conn.execute(f"INSERT INTO destination.{table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})", list(row.values()))
    return cursor.lastrowid


def transfer_subnet(source, target, subnet_id, authorize, *, expected_version=None, actor_id=None):
    try:
        with attached_transaction(source, target, write=expected_version is not None) as conn:
            authorize()
            root, data, version = snapshot(conn, subnet_id)
            summary = {"subnetId": subnet_id, "cidr": root["cidr"], "subnetCount": len(data["ipam_subnets"]),
                       "addressCount": len(data["ipam_addresses"]), "dhcpPoolCount": len(data["ipam_dhcp_pools"]),
                       "reservationCount": len(data["ipam_range_reservations"]), "tagCount": len(data["ipam_tags"]),
                       "scanCount": len(data["ipam_scans"]), "scheduleCount": len(data["ipam_scan_schedules"]),
                       "auditCount": len(data["ipam_audit_log"]), "version": version,
                       "sourceTenantId": source.tenant_id, "targetTenantId": target.tenant_id}
            for key, tenant_id in [("sourceTenantName", source.tenant_id), ("targetTenantName", target.tenant_id)]:
                summary[key] = conn.execute("SELECT name FROM main.tenants WHERE id = ?", (tenant_id,)).fetchone()[0]
            if expected_version is None:
                return summary
            if version != expected_version:
                raise TransferConflict("Subnet data changed since the preview. Review the move again")
            maps = {table: {} for table in ("ipam_subnets", "ipam_addresses", "ipam_dhcp_pools", "ipam_scans", "ipam_tags")}
            for table in ("ipam_subnets", *CHILD_TABLES):
                for original in data[table]:
                    row = dict(original)
                    old_id = row.pop("id", None)
                    if table == "ipam_subnets":
                        row["parent_id"] = maps[table].get(row["parent_id"])
                    else:
                        row["subnet_id"] = maps["ipam_subnets"][row["subnet_id"]]
                    if table == "ipam_scan_jobs":
                        row["id"] = str(uuid.uuid4())
                        if row["result_json"]:
                            result = json.loads(row["result_json"])
                            if "scanId" in result:
                                result["scanId"] = maps["ipam_scans"].get(result["scanId"])
                            row["result_json"] = json.dumps(result)
                    if table == "ipam_scan_schedules":
                        row.update(enabled=0, next_run_at=None)
                    new_id = insert(conn, table, row)
                    if table in maps:
                        maps[table][old_id] = new_id
            for original in data["ipam_tags"]:
                row = dict(original)
                old_id = row.pop("id")
                existing = conn.execute("SELECT id FROM destination.ipam_tags WHERE name = ?", (row["name"],)).fetchone()
                maps["ipam_tags"][old_id] = existing[0] if existing else insert(conn, "ipam_tags", row)
            for table, column, mapping in [("ipam_tag_subnets", "subnet_id", "ipam_subnets"), ("ipam_tag_addresses", "address_id", "ipam_addresses")]:
                for original in data[table]:
                    insert(conn, table, {"tag_id": maps["ipam_tags"][original["tag_id"]], column: maps[mapping][original[column]]})
            for original in data["ipam_audit_log"]:
                row = dict(original)
                row.pop("id")
                for column, table in [("subnet_id", "ipam_subnets"), ("address_id", "ipam_addresses"), ("dhcp_pool_id", "ipam_dhcp_pools")]:
                    row[column] = maps[table].get(row[column])
                insert(conn, "ipam_audit_log", row)
            # Keep original historical audit and archives in the source tenant.
            conn.execute("DELETE FROM origin.ipam_tag_addresses WHERE address_id IN (SELECT id FROM origin.ipam_addresses WHERE subnet_id IN (SELECT id FROM moving_subnets))")
            conn.execute("DELETE FROM origin.ipam_tag_subnets WHERE subnet_id IN (SELECT id FROM moving_subnets)")
            for table in reversed(CHILD_TABLES):
                conn.execute(f"DELETE FROM origin.{table} WHERE subnet_id IN (SELECT id FROM moving_subnets)")
            conn.execute("UPDATE origin.ipam_subnets SET parent_id = NULL WHERE id IN (SELECT id FROM moving_subnets)")
            conn.execute("DELETE FROM origin.ipam_subnets WHERE id IN (SELECT id FROM moving_subnets)")
            summary["targetSubnetId"] = maps["ipam_subnets"][subnet_id]
            details = json.dumps({k: v for k, v in summary.items() if k != "version"})
            now = auth_db._now()
            for alias, tenant_id, audit_subnet_id in [("origin", source.tenant_id, subnet_id), ("destination", target.tenant_id, summary["targetSubnetId"])]:
                conn.execute("INSERT INTO main.tenant_audit(tenant_id, actor_id, action, details, created_at) VALUES (?, ?, 'ipam_subnet_move', ?, ?)", (tenant_id, actor_id, details, now))
                conn.execute(f"INSERT INTO {alias}.ipam_audit_log(subnet_id, user_id, change_type, old_value, new_value, description, subnet_cidr, created_at) VALUES (?, ?, 'subnet_tenant_move', ?, ?, ?, ?, ?)", (audit_subnet_id, actor_id, json.dumps({"tenant": source.tenant_id}), json.dumps({"tenant": target.tenant_id}), f"Moved {root['cidr']} from {summary['sourceTenantName']} to {summary['targetTenantName']}", root["cidr"], now))
            return summary
    except sqlite3.IntegrityError as exc:
        raise TransferConflict("Move could not preserve data integrity; no data was moved") from exc
