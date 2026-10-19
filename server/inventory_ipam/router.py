import ipaddress
from typing import Literal
from device_visualization.schemas import DeviceCreate,DeviceDetail
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field
from dc_inventory.router import invoke
from . import repository


class PlacementRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expectedVersion:int=Field(strict=True,ge=1)


class HardwareCreateRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expectedUpdatedAt:str=Field(min_length=1,max_length=64)
    device:DeviceCreate
    ipPort:Literal['management','data']='management'


def build_router(require_feature,require_ipam_permission,require_logged_in_user):
    router=APIRouter(tags=['inventory-ipam'])

    @router.post('/api/device-visualization/devices/{device_id}/ports/{port_id}/ipam-placement',
        dependencies=[Depends(require_feature('device-visualization')),Depends(require_ipam_permission('write'))])
    def place(req:PlacementRequest,device_id:int=Path(ge=1),port_id:int=Path(ge=1),user=Depends(require_logged_in_user)):
        return invoke(repository.place_port,device_id,port_id,req.expectedVersion,user['id'] if user else None)

    @router.post('/api/ipam/addresses/{address_id}/hardware',response_model=DeviceDetail,status_code=201,
        dependencies=[Depends(require_ipam_permission('write')),Depends(require_feature('device-visualization'))])
    def create_hardware(req:HardwareCreateRequest,address_id:int=Path(ge=1),user=Depends(require_logged_in_user)):
        return invoke(repository.create_from_address,address_id,req,user['id'] if user else None)

    @router.get('/api/ipam/inventory-links',dependencies=[Depends(require_ipam_permission('read')),Depends(require_feature('dc-inventory'))])
    def links(address:str=Query(max_length=15),limit:int=Query(25,ge=1,le=100),offset:int=Query(0,ge=0)):
        try:
            ipaddress.IPv4Address(address)
        except ValueError:
            raise HTTPException(422,'Enter a valid IPv4 address')
        return invoke(repository.hardware_for_ip,address,limit,offset)
    return router
