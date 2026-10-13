import hashlib
import json
import sqlite3
from pathlib import Path

import auth_db


from tenancy.transfer import TransferConflict, HostNotFound, TransferUnavailable


def snapshot(conn, host):
    row = conn.execute("SELECT id, name, updated_at FROM origin.hosts WHERE name = ?", (host,)).fetchone()
    if row is None:
        raise HostNotFound()
    routes = [dict(r) for r in conn.execute("SELECT network, next_hop, interface FROM origin.routes WHERE host_id = ? ORDER BY id", (row["id"],))]
    interfaces = [dict(r) for r in conn.execute("SELECT name, ip_address, description FROM origin.interfaces WHERE host_id = ? ORDER BY id", (row["id"],))]
    data = {"name": row["name"], "updated_at": row["updated_at"], "routes": routes, "interfaces": interfaces}
    version = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    return row, routes, interfaces, version


def transfer(source, target, host, authorize, *, expected_version=None, actor_id=None):
    """One SQLite transaction spans source, target and central audit.

    Refuse WAL/OFF/MEMORY journals: multi-file crash atomicity requires
    file-backed main DB and persistent rollback journals (SQLite ATTACH).
    Schema aliases below are internal constants; paths come from the registry.
    """
    if Path(source.database_path).resolve() == Path(target.database_path).resolve():
        raise TransferConflict("Source and destination use the same database")
    conn = auth_db.get_connection()
    try:
        for alias, path in [("origin", source.database_path), ("destination", target.database_path)]:
            if not Path(path).is_file():
                raise TransferUnavailable("Tenant database is unavailable")
            conn.execute(f"ATTACH DATABASE ? AS {alias}", (str(path),))
        if expected_version is not None:
            for alias in ("main", "origin", "destination"):
                mode = conn.execute(f"PRAGMA {alias}.journal_mode").fetchone()[0]
                if mode.lower() not in ("delete", "truncate", "persist"):
                    raise TransferUnavailable("Moving hosts requires rollback-journal mode for all tenant and identity databases")
            conn.execute("BEGIN IMMEDIATE")
        else:
            conn.execute("BEGIN")
        authorize()  # Re-check live membership while identity writes are locked.
        row, routes, interfaces, version = snapshot(conn, host)
        if conn.execute("SELECT 1 FROM destination.hosts WHERE name = ?", (host,)).fetchone():
            raise TransferConflict("A host with this name already exists in the destination tenant")
        if expected_version is not None and version != expected_version:
            raise TransferConflict("Host changed since the preview. Review the move again")
        summary = {"host": host, "routeCount": len(routes), "interfaceCount": len(interfaces), "version": version,
                   "sourceTenantId": source.tenant_id, "targetTenantId": target.tenant_id}
        for key, tenant_id in [("sourceTenantName", source.tenant_id), ("targetTenantName", target.tenant_id)]:
            summary[key] = conn.execute("SELECT name FROM main.tenants WHERE id = ?", (tenant_id,)).fetchone()[0]
        if expected_version is None:
            return summary
        cursor = conn.execute("INSERT INTO destination.hosts(name, updated_at) VALUES (?, ?)", (row["name"], row["updated_at"]))
        target_host_id = cursor.lastrowid
        conn.executemany("INSERT INTO destination.routes(host_id, network, next_hop, interface) VALUES (?, ?, ?, ?)",
                         [(target_host_id, r["network"], r["next_hop"], r["interface"]) for r in routes])
        conn.executemany("INSERT INTO destination.interfaces(host_id, name, ip_address, description) VALUES (?, ?, ?, ?)",
                         [(target_host_id, i["name"], i["ip_address"], i["description"]) for i in interfaces])
        # Delete children explicitly: do not depend on attached-schema FK settings.
        conn.execute("DELETE FROM origin.routes WHERE host_id = ?", (row["id"],))
        conn.execute("DELETE FROM origin.interfaces WHERE host_id = ?", (row["id"],))
        conn.execute("DELETE FROM origin.hosts WHERE id = ?", (row["id"],))
        details = json.dumps({key: value for key, value in summary.items() if key != "version"})
        conn.executemany("INSERT INTO main.tenant_audit(tenant_id, actor_id, action, details, created_at) VALUES (?, ?, 'routing_host_move', ?, ?)",
                         [(tenant, actor_id, details, auth_db._now()) for tenant in [source.tenant_id, target.tenant_id]])
        conn.commit()
        return summary
    except sqlite3.IntegrityError as exc:
        raise TransferConflict("Move could not preserve data integrity; no data was moved") from exc
    except sqlite3.OperationalError as exc:
        raise TransferUnavailable("Tenant database is unavailable or busy. Retry the move") from exc
    finally:
        # Closing rolls back all three databases on every failure or preview.
        conn.close()
