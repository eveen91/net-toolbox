"""Tenant provisioning and server-verified database selection."""
import json
import os
import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException

import auth_db
import db
from .context import TenantContext, tenant_scope


def tenant_database_path(tenant):
    # Adopt the legacy database in-place; existing backups/deployments keep working.
    if tenant["is_default"]:
        return Path(db.DB_PATH)
    tenant_id = str(uuid.UUID(tenant["id"]))
    root = Path(os.environ.get("TENANT_DATA_ROOT", Path(db.DB_PATH).parent / "tenants"))
    return root / tenant_id / "toolbox.db"


def resolve_tenant(tenant_id, user):
    tenant = auth_db.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=403, detail="Tenant access denied")
    if user and user["role"] == auth_db.ADMIN_ROLE_NAME:
        role, permissions = "admin", ["*"]
    elif user:
        role = auth_db.tenant_role(tenant_id, user["id"])
        if role is None:
            raise HTTPException(status_code=403, detail="Tenant access denied")
        permissions = auth_db.role_permissions_for_name(role)
    elif tenant["is_default"] and not auth_db.is_login_required():
        role, permissions = None, ["*"]
    else:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return TenantContext(tenant_id, tenant_database_path(tenant), role, tuple(permissions))


def initialize_tenant(tenant):
    import troubleshoot_devices
    import troubleshoot_audit
    from device_visualization import repository as device_visualization
    path = tenant_database_path(tenant)
    with tenant_scope(TenantContext(tenant["id"], path)):
        db.init_db()
        troubleshoot_devices.init_db()
        troubleshoot_audit.init_db()
        device_visualization.init_db()


def initialize_all_tenants():
    conn = auth_db.get_connection()
    try:
        tenants = [dict(row) for row in conn.execute("SELECT * FROM tenants")]
    finally:
        conn.close()
    for tenant in tenants:
        initialize_tenant(tenant)


def create_tenant(name, actor_id):
    tenant = {"id": str(uuid.uuid4()), "name": name.strip(), "is_default": 0, "created_at": auth_db._now()}
    if not tenant["name"] or len(tenant["name"]) > 120:
        raise ValueError("Tenant name must contain 1–120 characters")
    directory = tenant_database_path(tenant).parent
    conn = auth_db.get_connection()
    created = False
    try:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM tenants WHERE name = ? COLLATE NOCASE", (tenant["name"],)).fetchone():
            raise ValueError("Tenant name already exists")
        directory.mkdir(parents=True, exist_ok=False, mode=0o700)
        created = True
        initialize_tenant(tenant)
        tenant_database_path(tenant).chmod(0o600)
        conn.execute("INSERT INTO tenants(id, name, is_default, created_at) VALUES (?, ?, 0, ?)",
                     (tenant["id"], tenant["name"], tenant["created_at"]))
        conn.execute("INSERT INTO tenant_audit(tenant_id, actor_id, action, details, created_at) VALUES (?, ?, 'tenant_create', ?, ?)",
                     (tenant["id"], actor_id, json.dumps({"name": tenant["name"]}), auth_db._now()))
        conn.commit()
        return tenant
    except Exception:
        conn.rollback()
        if created:
            shutil.rmtree(directory)
        raise
    finally:
        conn.close()
