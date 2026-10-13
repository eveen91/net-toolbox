from fastapi import HTTPException

import auth_db
from tenancy.context import current_tenant
from tenancy.service import resolve_tenant
from .repository import transfer, TransferConflict, HostNotFound, TransferUnavailable


def routing_access(context):
    if "*" not in context.permissions and "routing-map" not in context.permissions:
        raise HTTPException(status_code=403, detail="Routing Map permission is required in both tenants")


def move_targets(user):
    source = current_tenant.get()
    result = []
    for tenant in auth_db.list_tenants(user):
        if tenant["id"] == source.tenant_id:
            continue
        context = resolve_tenant(tenant["id"], user)
        if "*" in context.permissions or "routing-map" in context.permissions:
            result.append({"id": tenant["id"], "name": tenant["name"]})
    return result


def move_host(host, target_tenant_id, user, expected_version=None):
    source = current_tenant.get()
    if source.tenant_id == target_tenant_id:
        raise HTTPException(status_code=400, detail="Select a different destination tenant")
    target = resolve_tenant(target_tenant_id, user)
    routing_access(source)
    routing_access(target)

    def authorize():
        fresh_user = auth_db.get_user_by_id(user["id"])
        if fresh_user is None:
            raise HTTPException(status_code=403, detail="Account access has been revoked")
        routing_access(resolve_tenant(source.tenant_id, fresh_user))
        routing_access(resolve_tenant(target.tenant_id, fresh_user))

    try:
        return transfer(source, target, host, authorize, expected_version=expected_version, actor_id=user["id"])
    except HostNotFound:
        raise HTTPException(status_code=404, detail="Host not found in the source tenant")
    except TransferConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except TransferUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
