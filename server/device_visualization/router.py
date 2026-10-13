import sqlite3
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from . import service, repository
from .schemas import (DeviceCreate, DeviceUpdate, DeviceDelete, PortAssignment,
                      DeviceDetail, DevicePage, PreviewResponse, AuditPage, DeviceType, Vendor)


def invoke(operation, *args, **kwargs):
    try:
        return service.execute(operation, *args, **kwargs)
    except repository.Missing:
        raise HTTPException(404, 'Device, network card or port not found')
    except repository.Conflict as exc:
        raise HTTPException(409, exc.detail)
    except repository.Invalid as exc:
        raise HTTPException(400, str(exc))
    except sqlite3.OperationalError:
        raise HTTPException(503, 'Device storage is busy or unavailable. Retry shortly')


def build_router(require_feature, require_logged_in_user):
    router=APIRouter(prefix='/api/device-visualization',tags=['device-visualization'],
                     dependencies=[Depends(require_feature('device-visualization'))])

    @router.get('/devices',response_model=DevicePage)
    def listing(query: str=Query(default='',max_length=100),deviceType: DeviceType | None=None,vendor: Vendor | None=None,
                limit: int=Query(default=50,ge=1,le=100),offset: int=Query(default=0,ge=0)):
        if vendor and deviceType and deviceType!='firewall':
            raise HTTPException(422,'Vendor filter is only supported for firewalls')
        return invoke('list_devices',query.strip(),deviceType,vendor,limit,offset)

    @router.post('/devices',response_model=DeviceDetail,status_code=201,response_model_exclude_none=False)
    def create(req: DeviceCreate,user=Depends(require_logged_in_user)):
        return invoke('create_device',req,actor_id=user['id'] if user else None)

    @router.get('/devices/{device_id}',response_model=DeviceDetail)
    def detail(device_id: int=Path(ge=1)):
        return invoke('get_device',device_id)

    @router.post('/devices/{device_id}/update-preview',response_model=PreviewResponse)
    def preview(req: DeviceUpdate,device_id: int=Path(ge=1)):
        return invoke('update_device',device_id,req,preview=True)

    @router.put('/devices/{device_id}',response_model=DeviceDetail)
    def update(req: DeviceUpdate,device_id: int=Path(ge=1),user=Depends(require_logged_in_user)):
        return invoke('update_device',device_id,req,actor_id=user['id'] if user else None)

    @router.put('/devices/{device_id}/ports/{port_id}',response_model=DeviceDetail)
    def assignment(req: PortAssignment,device_id: int=Path(ge=1),port_id: int=Path(ge=1),user=Depends(require_logged_in_user)):
        return invoke('update_port',device_id,port_id,req,actor_id=user['id'] if user else None)

    @router.delete('/devices/{device_id}')
    def delete(req: DeviceDelete,device_id: int=Path(ge=1),user=Depends(require_logged_in_user)):
        return invoke('delete_device',device_id,req,actor_id=user['id'] if user else None)

    @router.get('/devices/{device_id}/audit',response_model=AuditPage)
    def history(device_id: int=Path(ge=1),limit: int=Query(default=50,ge=1,le=100),offset: int=Query(default=0,ge=0)):
        return invoke('list_audit',device_id,limit,offset)

    return router
