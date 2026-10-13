from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException
from pydantic import BaseModel, Field

import auth_db
from .service import create_tenant, resolve_tenant


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class MembershipUpdate(BaseModel):
    role: str = Field(min_length=1, max_length=120)


def build_router(require_platform_admin):
    router = APIRouter(prefix="/api/tenants", tags=["tenants"])

    def identity(session_token: Optional[str] = Cookie(default=None)):
        return auth_db.get_user_by_session_token(session_token) if session_token else None

    def tenant_admin(tenant_id: str, user=Depends(identity)):
        context = resolve_tenant(tenant_id, user)
        if user is None or (user["role"] != "admin" and context.role != "tenant-admin"):
            raise HTTPException(status_code=403, detail="Tenant administrator access required")
        return user

    @router.get("")
    def accessible_tenants(user=Depends(identity)):
        return auth_db.list_tenants(user)

    @router.post("", status_code=201)
    def provision(req: TenantCreate, user=Depends(require_platform_admin)):
        if user is None:
            raise HTTPException(status_code=401, detail="Create a platform administrator first")
        try:
            return create_tenant(req.name, user["id"])
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

    @router.get("/{tenant_id}/members")
    def members(tenant_id: str, user=Depends(tenant_admin)):
        return auth_db.list_tenant_members(tenant_id)

    @router.get("/{tenant_id}/roles")
    def membership_roles(tenant_id: str, user=Depends(tenant_admin)):
        return [role for role in auth_db.list_roles() if role["name"] != "admin"]

    @router.get("/{tenant_id}/users")
    def assignable_users(tenant_id: str, user=Depends(tenant_admin)):
        # Only platform admins can enumerate global accounts. Tenant admins
        # see and manage existing members of their own tenant.
        if user["role"] != "admin":
            return auth_db.list_tenant_members(tenant_id)
        return [{"id": u["id"], "username": u["username"], "authSource": u["authSource"]}
                for u in auth_db.list_users()]

    @router.put("/{tenant_id}/members/{user_id}")
    def grant(tenant_id: str, user_id: int, req: MembershipUpdate, user=Depends(tenant_admin)):
        # Tenant administrators may manage users already visible in their tenant.
        if user["role"] != "admin" and auth_db.tenant_role(tenant_id, user_id) is None:
            raise HTTPException(status_code=403, detail="Platform administrator must grant initial membership")
        try:
            auth_db.set_tenant_membership(tenant_id, user_id, req.role, user["id"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"ok": True}

    @router.delete("/{tenant_id}/members/{user_id}")
    def revoke(tenant_id: str, user_id: int, user=Depends(tenant_admin)):
        auth_db.remove_tenant_membership(tenant_id, user_id, user["id"])
        return {"ok": True}

    @router.get("/{tenant_id}/audit")
    def tenant_audit(tenant_id: str, user=Depends(tenant_admin)):
        conn = auth_db.get_connection()
        try:
            return [dict(row) for row in conn.execute(
                "SELECT a.*, u.username AS actor_username FROM tenant_audit a LEFT JOIN users u ON u.id = a.actor_id WHERE a.tenant_id = ? ORDER BY a.id DESC LIMIT 200", (tenant_id,))]
        finally:
            conn.close()

    return router
