from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, Field
from .service import move_targets, move_subnet


class MoveSubnetRequest(BaseModel):
    targetTenantId: str = Field(min_length=1, max_length=64)
    expectedVersion: str = Field(pattern=r"^[0-9a-f]{64}$")


def build_router(require_ipam_permission, require_authenticated_user):
    router = APIRouter(prefix="/api/ipam", tags=["ipam"], dependencies=[Depends(require_ipam_permission("write"))])

    @router.get("/move-targets")
    def targets(user=Depends(require_authenticated_user)):
        return move_targets(user)

    @router.get("/subnets/{subnet_id}/move-preview")
    def preview(subnet_id: int = Path(ge=1), targetTenantId: str = Query(min_length=1, max_length=64), user=Depends(require_authenticated_user)):
        return move_subnet(subnet_id, targetTenantId, user)

    @router.post("/subnets/{subnet_id}/move")
    def move(req: MoveSubnetRequest, subnet_id: int = Path(ge=1), user=Depends(require_authenticated_user)):
        return move_subnet(subnet_id, req.targetTenantId, user, req.expectedVersion)

    return router
