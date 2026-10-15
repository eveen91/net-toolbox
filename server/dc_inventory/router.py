import sqlite3
from fastapi import APIRouter,Depends,HTTPException,Query,Path
from device_visualization import repository as devices
from . import repository as repo,service
from .schemas import DataCenterWrite,DataCenterUpdate,RackCreate,RackUpdate,ResourceDelete,Placement,CablePanelCreate


def invoke(operation,*args,**kwargs):
    try:return operation(*args,**kwargs)
    except devices.Missing:raise HTTPException(404,'Data centre, rack or device not found')
    except devices.Conflict as exc:raise HTTPException(409,exc.detail)
    except devices.Invalid as exc:raise HTTPException(400,str(exc))
    except sqlite3.OperationalError:raise HTTPException(503,'Inventory storage is busy or unavailable. Retry shortly')


def catalog_router():
    router=APIRouter()
    @router.get('/datacenters')
    def datacenters(limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0)):
        return invoke(repo.datacenters,limit,offset)
    @router.get('/racks')
    def racks(dataCenterId:int|None=Query(None,ge=1),limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0)):
        return invoke(repo.racks,dataCenterId,limit,offset)
    return router


def build_router(require_feature,require_logged_in_user):
    router=APIRouter(prefix='/api/dc-inventory',tags=['dc-inventory'],dependencies=[Depends(require_feature('dc-inventory'))])
    router.include_router(catalog_router())
    def actor(user):return user['id'] if user else None
    @router.post('/datacenters',status_code=201)
    def create_dc(req:DataCenterWrite,user=Depends(require_logged_in_user)):
        return invoke(service.mutate,'datacenter',req,actor=actor(user))
    @router.put('/datacenters/{entity_id}')
    def update_dc(req:DataCenterUpdate,entity_id:int=Path(ge=1),user=Depends(require_logged_in_user)):
        return invoke(service.mutate,'datacenter',req,entity_id,actor(user))
    @router.delete('/datacenters/{entity_id}')
    def delete_dc(req:ResourceDelete,entity_id:int=Path(ge=1),user=Depends(require_logged_in_user)):
        return invoke(service.mutate,'datacenter',req,entity_id,actor(user),True)
    @router.post('/racks',status_code=201)
    def create_rack(req:RackCreate,user=Depends(require_logged_in_user)):
        return invoke(service.mutate,'rack',req,actor=actor(user))
    @router.get('/racks/{rack_id}')
    def detail(rack_id:int=Path(ge=1)):
        return invoke(repo.rack_detail,rack_id)
    @router.put('/racks/{entity_id}')
    def update_rack(req:RackUpdate,entity_id:int=Path(ge=1),user=Depends(require_logged_in_user)):
        return invoke(service.mutate,'rack',req,entity_id,actor(user))
    @router.delete('/racks/{entity_id}')
    def delete_rack(req:ResourceDelete,entity_id:int=Path(ge=1),user=Depends(require_logged_in_user)):
        return invoke(service.mutate,'rack',req,entity_id,actor(user),True)
    @router.post('/cable-panels',status_code=201)
    def create_panel(req:CablePanelCreate,user=Depends(require_logged_in_user)):
        return invoke(service.create_cable_panel,req,actor(user))
    @router.get('/devices')
    def listing(unassigned:bool=False,rackId:int|None=Query(None,ge=1),query:str=Query('',max_length=100),limit:int=Query(25,ge=1,le=100),offset:int=Query(0,ge=0)):
        return invoke(repo.device_page,unassigned,rackId,query.strip(),limit,offset)
    @router.put('/devices/{device_id}/placement')
    def placement(req:Placement,device_id:int=Path(ge=1),user=Depends(require_logged_in_user)):
        return invoke(service.place,device_id,req,actor(user))
    @router.get('/audit')
    def audit(limit:int=Query(25,ge=1,le=100),offset:int=Query(0,ge=0)):
        return invoke(repo.history,limit,offset)
    return router
