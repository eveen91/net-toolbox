import json
import auth
import auth_db
import db
from tenancy.context import tenant_scope
from tenancy.service import resolve_tenant


def setup(client):
    admin = auth_db.create_user("transfer-admin", auth.hash_password("Password123"), role="admin")
    client.post("/api/auth/login", json={"username": "transfer-admin", "password": "Password123"})
    target = client.post("/api/tenants", json={"name": "Target IPAM"}).json()["id"]
    root = client.post("/api/ipam/subnets", json={"cidr": "10.40.0.0/16", "vlan": 120, "description": "root"}).json()["id"]
    child = client.post("/api/ipam/subnets", json={"cidr": "10.40.1.0/24", "description": "nested"}).json()["id"]
    return admin, target, root, child


def preview(client, root, target):
    return client.get(f"/api/ipam/subnets/{root}/move-preview", params={"targetTenantId": target})


def move(client, root, target, version):
    return client.post(f"/api/ipam/subnets/{root}/move", json={"targetTenantId": target, "expectedVersion": version})


def test_move_tree_preserves_relations_history_and_pauses_schedule(client):
    admin, target, root, child = setup(client)
    now = auth_db._now()
    # Occupy target IDs to verify actual FK remapping rather than coincidental equality.
    client.post("/api/ipam/subnets", headers={"X-Tenant-ID": target}, json={"cidr": "192.168.1.0/24"})
    conn = db.get_connection()
    address = conn.execute("INSERT INTO ipam_addresses(subnet_id,address,status,hostname,locked,team,updated_at) VALUES (?, '10.40.1.10', 'reserved', 'web01', 1, 'ops', ?)", (child, now)).lastrowid
    pool = conn.execute("INSERT INTO ipam_dhcp_pools(subnet_id,start_ip,end_ip,name,description,manually_placed,updated_at) VALUES (?, '10.40.1.100','10.40.1.150','pool','description',1,?)", (child, now)).lastrowid
    conn.execute("INSERT INTO ipam_range_reservations(subnet_id,start_ip,end_ip,label,created_at,updated_at) VALUES (?, '10.40.1.50','10.40.1.60','reserved',?,?)", (child, now, now))
    conn.execute("INSERT INTO ipam_scan_excludes(subnet_id,address) VALUES (?, '10.40.1.20')", (child,))
    conn.execute("INSERT INTO ipam_scan_schedules(subnet_id,interval_minutes,enabled,updated_at) VALUES (?,60,1,?)", (child, now))
    scan = conn.execute("INSERT INTO ipam_scans(subnet_id,started_at,finished_at,scanned_count,used_count,free_count,skipped_count,newly_used_count,went_quiet_count,hostname_changed_count,diff_json) VALUES (?,?,?,1,1,0,0,1,0,0,'{}')", (child, now, now)).lastrowid
    conn.execute("INSERT INTO ipam_scan_jobs(id,subnet_id,status,result_json,created_at,updated_at) VALUES ('old-job',?,'done',?,?,?)", (child, json.dumps({"scanId": scan}), now, now))
    tag = conn.execute("INSERT INTO ipam_tags(name,color,description,created_at,updated_at) VALUES ('Ops','#123456','team',?,?)", (now, now)).lastrowid
    conn.execute("INSERT INTO ipam_tag_subnets VALUES (?,?)", (tag, root))
    conn.execute("INSERT INTO ipam_tag_addresses VALUES (?,?)", (tag, address))
    conn.execute("INSERT INTO ipam_audit_log(address_id,subnet_id,dhcp_pool_id,user_id,change_type,subnet_cidr,created_at) VALUES (?,?,?,?,'update','10.40.1.0/24',?)", (address, child, pool, admin["id"], now))
    conn.commit(); conn.close()
    reviewed = preview(client, root, target)
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["subnetCount"] == 2
    result = move(client, root, target, reviewed.json()["version"])
    assert result.status_code == 200, result.text
    assert client.get(f"/api/ipam/subnets/{root}").status_code == 404
    assert client.get(f"/api/ipam/subnets/{child}").status_code == 404
    with tenant_scope(resolve_tenant(target, admin)):
        conn = db.get_connection()
        new_root = conn.execute("SELECT * FROM ipam_subnets WHERE cidr='10.40.0.0/16'").fetchone()
        new_child = conn.execute("SELECT * FROM ipam_subnets WHERE cidr='10.40.1.0/24'").fetchone()
        assert new_root["vlan"] == 120 and new_root["id"] != root
        assert new_child["parent_id"] == new_root["id"]
        a = conn.execute("SELECT * FROM ipam_addresses").fetchone()
        assert (a["subnet_id"], a["locked"], a["hostname"], a["team"]) == (new_child["id"], 1, "web01", "ops")
        assert conn.execute("SELECT name FROM ipam_dhcp_pools").fetchone()[0] == "pool"
        assert conn.execute("SELECT enabled FROM ipam_scan_schedules").fetchone()[0] == 0
        for table in ["ipam_scan_excludes", "ipam_range_reservations", "ipam_tag_addresses", "ipam_tag_subnets"]:
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 1
        audit = conn.execute("SELECT * FROM ipam_audit_log WHERE change_type='update'").fetchone()
        assert audit["address_id"] == a["id"] and audit["subnet_id"] == new_child["id"]
        job = conn.execute("SELECT * FROM ipam_scan_jobs").fetchone()
        assert job["id"] != "old-job"
        assert json.loads(job["result_json"])["scanId"] == conn.execute("SELECT id FROM ipam_scans").fetchone()[0]
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        conn.close()
    for tenant in ["default", target]:
        assert client.get(f"/api/tenants/{tenant}/audit").json()[0]["action"] == "ipam_subnet_move"


def test_stale_preview_overlap_and_active_scans_block_move(client):
    _, target, root, child = setup(client)
    reviewed = preview(client, root, target).json()
    conn = db.get_connection()
    conn.execute("UPDATE ipam_subnets SET description='edited' WHERE id=?", (child,)); conn.commit(); conn.close()
    assert move(client, root, target, reviewed["version"]).status_code == 409
    now = auth_db._now()
    conn = db.get_connection()
    conn.execute("INSERT INTO ipam_scan_jobs(id,subnet_id,status,created_at,updated_at) VALUES ('active',?,'running',?,?)", (child, now, now)); conn.commit(); conn.close()
    assert preview(client, root, target).status_code == 409
    conn = db.get_connection(); conn.execute("DELETE FROM ipam_scan_jobs"); conn.commit(); conn.close()
    client.post("/api/ipam/subnets", headers={"X-Tenant-ID": target}, json={"cidr": "10.40.2.0/24"})
    assert preview(client, root, target).status_code == 409
    assert client.get(f"/api/ipam/subnets/{root}").status_code == 200
    assert preview(client, root, "default").status_code == 400


def test_audit_failure_rolls_back_all_databases(client):
    _, target, root, child = setup(client)
    reviewed = preview(client, root, target).json()
    conn = auth_db.get_connection()
    conn.execute("CREATE TRIGGER reject_ipam_move BEFORE INSERT ON tenant_audit WHEN NEW.action='ipam_subnet_move' BEGIN SELECT RAISE(ABORT,'audit failure'); END")
    conn.commit(); conn.close()
    assert move(client, root, target, reviewed["version"]).status_code == 409
    assert client.get(f"/api/ipam/subnets/{child}").status_code == 200
    assert client.get("/api/ipam/subnets", headers={"X-Tenant-ID": target}).json() == []


def test_write_permissions_membership_and_login_required_in_both_tenants(client):
    _, target, root, _ = setup(client)
    auth_db.create_role("transfer-writer", ["ipam.read", "ipam.write"])
    auth_db.create_role("transfer-reader", ["ipam.read"])
    member = auth_db.create_user("transfer-member", auth.hash_password("Password123"), role="transfer-writer")
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "transfer-member", "password": "Password123"})
    assert client.get("/api/ipam/move-targets").json() == []
    assert preview(client, root, target).status_code == 403
    auth_db.set_tenant_membership(target, member["id"], "transfer-reader")
    assert preview(client, root, target).status_code == 403
    auth_db.set_tenant_membership(target, member["id"], "transfer-writer")
    reviewed = preview(client, root, target).json()
    auth_db.remove_tenant_membership(target, member["id"])
    assert move(client, root, target, reviewed["version"]).status_code == 403
    client.post("/api/auth/logout")
    assert client.get("/api/ipam/move-targets").status_code == 401


def test_tag_conflict_blocks_transfer_and_identical_tag_is_reused(client):
    admin, target, root, _ = setup(client)
    now = auth_db._now()
    conn = db.get_connection()
    tag = conn.execute("INSERT INTO ipam_tags(name,color,description,created_at,updated_at) VALUES ('Shared','#123456','description',?,?)", (now, now)).lastrowid
    conn.execute("INSERT INTO ipam_tag_subnets VALUES (?,?)", (tag, root))
    conn.commit(); conn.close()
    with tenant_scope(resolve_tenant(target, admin)):
        conn = db.get_connection()
        target_tag = conn.execute("INSERT INTO ipam_tags(name,color,description,created_at,updated_at) VALUES ('Shared','#654321','description',?,?)", (now, now)).lastrowid
        conn.commit(); conn.close()
    assert preview(client, root, target).status_code == 409
    with tenant_scope(resolve_tenant(target, admin)):
        conn = db.get_connection()
        conn.execute("UPDATE ipam_tags SET color='#123456' WHERE id=?", (target_tag,))
        conn.commit(); conn.close()
    reviewed = preview(client, root, target).json()
    result = move(client, root, target, reviewed["version"])
    assert result.status_code == 200
    with tenant_scope(resolve_tenant(target, admin)):
        conn = db.get_connection()
        assert conn.execute("SELECT COUNT(*) FROM ipam_tags").fetchone()[0] == 1
        assert conn.execute("SELECT tag_id FROM ipam_tag_subnets").fetchone()[0] == target_tag
        conn.close()


def test_moving_child_detaches_from_source_parent_and_blocks_overlap_on_return(client):
    _, target, root, child = setup(client)
    reviewed = preview(client, child, target).json()
    assert reviewed["subnetCount"] == 1
    result = move(client, child, target, reviewed["version"])
    assert result.status_code == 200
    assert client.get(f"/api/ipam/subnets/{root}").status_code == 200
    moved_id = result.json()["targetSubnetId"]
    headers = {"X-Tenant-ID": target}
    assert client.get(f"/api/ipam/subnets/{moved_id}", headers=headers).json()["parentId"] is None
    # The source parent is an overlap, so a return move is explicitly blocked.
    response = client.get(f"/api/ipam/subnets/{moved_id}/move-preview", headers=headers, params={"targetTenantId": "default"})
    assert response.status_code == 409


def test_wal_database_rejects_move_without_changes(client):
    _, target, root, _ = setup(client)
    reviewed = preview(client, root, target).json()
    conn = auth_db.get_connection()
    conn.execute("PRAGMA journal_mode=WAL"); conn.close()
    assert move(client, root, target, reviewed["version"]).status_code == 503
    assert client.get(f"/api/ipam/subnets/{root}").status_code == 200
    assert client.get("/api/ipam/subnets", headers={"X-Tenant-ID": target}).json() == []


def test_concurrent_confirmation_moves_tree_once(client):
    from concurrent.futures import ThreadPoolExecutor
    _, target, root, _ = setup(client)
    version = preview(client, root, target).json()["version"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: move(client, root, target, version).status_code, range(2)))
    assert sorted(results) == [200, 404]
    assert len(client.get("/api/ipam/subnets", headers={"X-Tenant-ID": target}).json()) == 2
    moves = [event for event in client.get(f"/api/tenants/{target}/audit").json() if event["action"] == "ipam_subnet_move"]
    assert len(moves) == 1
