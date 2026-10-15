import sqlite3
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from .repository import import_networks, Missing, Conflict


class ImportInterfaces(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expectedUpdatedAt: str = Field(min_length=1,max_length=64)
    interfaces: list[str] | None = Field(default=None,min_length=1,max_length=1000)


def build_router(require_feature,require_ipam_permission,require_logged_in_user):
    router = APIRouter(prefix='/api/routing',tags=['routing-ipam'],
                       dependencies=[Depends(require_feature('routing-map')),Depends(require_ipam_permission('write'))])

    @router.post('/hosts/{host}/ipam-import')
    def import_interfaces(host: str,req: ImportInterfaces,user=Depends(require_logged_in_user)):
        try:
            return import_networks(host,req.expectedUpdatedAt,req.interfaces,user['id'] if user else None)
        except Missing as exc:
            raise HTTPException(404,str(exc))
        except Conflict as exc:
            raise HTTPException(409,str(exc))
        except ValueError as exc:
            raise HTTPException(422,str(exc))
        except sqlite3.Error:
            raise HTTPException(503,'IPAM import could not be saved. No new subnets were committed; retry shortly')

    return router
