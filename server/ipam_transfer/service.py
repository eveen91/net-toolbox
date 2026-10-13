from fastapi import HTTPException

import auth_db
from tenancy.context import current_tenant
from tenancy.service import resolve_tenant
from tenancy.transfer import TransferConflict, HostNotFound, TransferUnavailable
from .repository import transfer_subnet


def write_access(context):
    if not {"*", "ipam", "ipam.write"}.intersection(context.permissions):
        raise HTTPException(status_code=403, detail="IPAM write permission is required in both tenants")


def move_targets(user):
    source = current_tenant.get()
    write_access(source)
    result = []
    for tenant in auth_db.list_tenants(user):
        if tenant["id"] == source.tenant_id:
            continue
        context = resolve_tenant(tenant["id"], user)
        if {"*", "ipam", "ipam.write"}.intersection(context.permissions):
            result.append({"id": tenant["id"], "name": tenant["name"]})
    return result


def move_subnet(subnet_id, target_tenant_id, user, expected_version=None):
    source = current_tenant.get()
    if source.tenant_id == target_tenant_id:
        raise HTTPException(status_code=400, detail="Select a different destination tenant")
    target = resolve_tenant(target_tenant_id, user)
    write_access(source)
    write_access(target)

    def authorize():
        fresh_user = auth_db.get_user_by_id(user["id"])
        if fresh_user is None:
            raise HTTPException(status_code=403, detail="Account access has been revoked")
        write_access(resolve_tenant(source.tenant_id, fresh_user))
        write_access(resolve_tenant(target_tenant_id, fresh_user))

    try:
        return transfer_subnet(source, target, subnet_id, authorize, expected_version=expected_version, actor_id=user["id"])
    except HostNotFound:
        raise HTTPException(status_code=404, detail="Subnet not found in the source tenant")
    except TransferConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except TransferUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
