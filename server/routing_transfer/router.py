from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from .service import move_targets, move_host


class MoveHostRequest(BaseModel):
    targetTenantId: str = Field(min_length=1, max_length=64)
    expectedVersion: str = Field(pattern=r"^[0-9a-f]{64}$")


def build_router(require_feature, require_authenticated_user):
    router = APIRouter(prefix="/api/routing", tags=["routing"], dependencies=[Depends(require_feature("routing-map"))])

    @router.get("/move-targets")
    def targets(user=Depends(require_authenticated_user)):
        return move_targets(user)

    @router.get("/hosts/{host}/move-preview")
    def preview(host: str, targetTenantId: str = Query(min_length=1, max_length=64), user=Depends(require_authenticated_user)):
        return move_host(host, targetTenantId, user)

    @router.post("/hosts/{host}/move")
    def move(host: str, req: MoveHostRequest, user=Depends(require_authenticated_user)):
        return move_host(host, req.targetTenantId, user, req.expectedVersion)

    return router
