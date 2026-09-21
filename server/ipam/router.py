import csv
import io
import ipaddress
import json
import sqlite3
from datetime import datetime
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from . import scan_service as scans
from .schemas import *
from .service import IpamService


AUDIT_CHANGE_TYPES = frozenset({
    "create",
    "update",
    "delete",
    "reassign",
    "subnet_create",
    "subnet_update",
    "subnet_delete",
    "dhcp_pool_create",
    "dhcp_pool_update",
    "dhcp_pool_delete",
    "dhcp_pool_move",
    "dhcp_pool_bulk_move",
    "tag_create",
    "tag_delete",
    "subnet_tag_add",
    "subnet_tag_remove",
    "address_tag_add",
    "address_tag_remove",
    "settings_update",
})


def _audit_filters(
    start_time: Optional[str],
    end_time: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    change_type: Optional[List[str]],
    change_types: Optional[List[str]],
):
    start = start_time or (f"{start_date}T00:00:00+00:00" if start_date and "T" not in start_date else start_date)
    end = end_time or (f"{end_date}T23:59:59.999999+00:00" if end_date and "T" not in end_date else end_date)
    try:
        start_value = datetime.fromisoformat(start.replace("Z", "+00:00")) if start else None
        end_value = datetime.fromisoformat(end.replace("Z", "+00:00")) if end else None
        if start_value and end_value:
            if (start_value.tzinfo is None) != (end_value.tzinfo is None):
                raise ValueError
            if start_value > end_value:
                raise HTTPException(status_code=400, detail="Audit start time must not be after end time")
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Audit dates must be valid ISO 8601 values with matching time zones")
    selected_types = (change_type or []) + (change_types or [])
    invalid_types = sorted(set(selected_types) - AUDIT_CHANGE_TYPES)
    if invalid_types:
        raise HTTPException(status_code=422, detail=f"Unsupported audit change type: {', '.join(invalid_types)}")
    return start, end, selected_types


def _audit_csv_response(service: IpamService, **filters) -> Response:
    page = service.query_audit_log(limit=1_000_000, offset=0, **filters)
    output = io.StringIO(newline="")
    fieldnames = [
        "id", "createdAt", "changeType", "username", "userId", "subnetId",
        "addressId", "dhcpPoolId", "ipAddress", "subnetCidr", "description",
        "oldValue", "newValue",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for entry in page["entries"]:
        row = {key: entry.get(key) for key in fieldnames}
        row["oldValue"] = json.dumps(row["oldValue"], ensure_ascii=False) if row["oldValue"] is not None else ""
        row["newValue"] = json.dumps(row["newValue"], ensure_ascii=False) if row["newValue"] is not None else ""
        writer.writerow(row)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="ipam-audit.csv"'},
    )


def build_router(service: IpamService, require_ipam_permission, require_logged_in_user) -> APIRouter:
    router = APIRouter()

    @router.get("/api/ipam/dashboard", response_model=List[DashboardEntry], dependencies=[Depends(require_ipam_permission("read"))])
    def get_ipam_dashboard():
        return service.get_ipam_dashboard()


    @router.get("/api/ipam/subnets", response_model=List[SubnetSummary], dependencies=[Depends(require_ipam_permission("read"))])
    def get_subnets():
        return service.list_subnets()


    @router.get(
        "/api/ipam/misplaced-addresses",
        response_model=List[MisplacedAddressEntry],
        dependencies=[Depends(require_ipam_permission("read"))],
    )
    def get_misplaced_addresses():
        return service.list_misplaced_addresses()


    @router.post(
        "/api/ipam/subnets/{subnet_id}/allocate-next",
        response_model=AllocateNextAddressResponse,
        dependencies=[Depends(require_ipam_permission("write"))],
    )
    def allocate_next_address(subnet_id: int, req: AllocateNextAddressRequest, user: Optional[Dict] = Depends(require_logged_in_user)):
        try:
            return service.allocate_next_address(
                subnet_id, req.status, req.hostname, req.description, req.team,
                req.machineType, req.vmCluster, req.environment, req.locked,
                user_id=user["id"] if user else None,
            )
        except ValueError as exc:
            status_code = 404 if str(exc) == "Subnet not found" else 400
            raise HTTPException(status_code=status_code, detail=str(exc))


    @router.get(
        "/api/ipam/subnets/{subnet_id}/next-available",
        response_model=NextAvailableIpResponse,
        dependencies=[Depends(require_ipam_permission("read"))],
    )
    def get_next_available_ip(subnet_id: int):
        if not service.subnet_exists(subnet_id):
            raise HTTPException(status_code=404, detail="Subnet not found")
        try:
            ip = service.get_next_available_ip(subnet_id)
            return NextAvailableIpResponse(subnetId=subnet_id, nextAvailableIp=ip)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))


    @router.get(
        "/api/ipam/misplaced-dhcp-pools",
        response_model=List[MisplacedDhcpPoolEntry],
        dependencies=[Depends(require_ipam_permission("read"))],
    )
    def get_misplaced_dhcp_pools():
        return service.list_misplaced_dhcp_pools()


    @router.get(
        "/api/ipam/addresses/search",
        response_model=List[SearchAddressEntry],
        dependencies=[Depends(require_ipam_permission("read"))],
    )
    def search_ipam_addresses(q: str = ""):
        return service.search_addresses(q)


    @router.get("/api/ipam/settings", response_model=IpamSettingsResponse, dependencies=[Depends(require_ipam_permission("admin"))])
    def get_ipam_settings():
        return IpamSettingsResponse(
            scanConcurrencyLimit=service.get_scan_concurrency_limit(),
            scanConcurrencyMin=service.SCAN_CONCURRENCY_MIN,
            scanConcurrencyMax=service.SCAN_CONCURRENCY_MAX,
        )


    @router.put("/api/ipam/settings", response_model=IpamSettingsResponse, dependencies=[Depends(require_ipam_permission("admin"))])
    def update_ipam_settings(req: UpdateIpamSettingsRequest, user: Optional[Dict] = Depends(require_logged_in_user)):
        try:
            service.set_scan_concurrency_limit(req.scanConcurrencyLimit, user_id=user["id"] if user else None)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return IpamSettingsResponse(
            scanConcurrencyLimit=service.get_scan_concurrency_limit(),
            scanConcurrencyMin=service.SCAN_CONCURRENCY_MIN,
            scanConcurrencyMax=service.SCAN_CONCURRENCY_MAX,
        )


    @router.post("/api/ipam/subnets", response_model=SubnetSummary, dependencies=[Depends(require_ipam_permission("write"))])
    def create_subnet(req: SubnetRequest, user: Optional[Dict] = Depends(require_logged_in_user)):
        try:
            user_id = user["id"] if user else None
            return service.create_subnet(req.cidr, req.vlan, req.description, user_id=user_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))


    @router.post("/api/ipam/allocation-plan/create", response_model=SubnetSummary, dependencies=[Depends(require_ipam_permission("write"))])
    def create_allocated_subnet(req: CreateAllocatedSubnetRequest, user: Optional[Dict] = Depends(require_logged_in_user)):
        try:
            return service.create_allocated_subnet(
                req.parent, req.cidr, req.freshnessToken, req.vlan, req.description, req.tagIds,
                user_id=user["id"] if user else None,
            )
        except ValueError as exc:
            detail = str(exc)
            status_code = 409 if detail.startswith("Allocation state is stale") or "overlaps" in detail else 400
            raise HTTPException(status_code=status_code, detail=detail)


    @router.get("/api/ipam/subnets/{subnet_id}", response_model=SubnetSummary, dependencies=[Depends(require_ipam_permission("read"))])
    def get_subnet(subnet_id: int):
        data = service.get_subnet(subnet_id)
        if data is None:
            raise HTTPException(status_code=404, detail="Subnet not found")
        return data


    @router.get(
        "/api/ipam/subnets/{subnet_id}/addresses",
        response_model=AddressPageResponse,
        dependencies=[Depends(require_ipam_permission("read"))],
    )
    def get_subnet_addresses(
        subnet_id: int,
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        status: Optional[Literal["used", "free", "reserved"]] = None,
        team: Optional[str] = Query(default=None, max_length=100),
        environment: Optional[Literal["prod", "test", "dev"]] = None,
        machine_type: Optional[Literal["physical", "vm"]] = None,
        tag_id: Optional[int] = Query(default=None, gt=0),
        query: Optional[str] = Query(default=None, max_length=253),
        sort: Literal["address", "status", "hostname", "updatedAt"] = "address",
        direction: Literal["asc", "desc"] = "asc",
        address_start: Optional[ipaddress.IPv4Address] = None,
        address_end: Optional[ipaddress.IPv4Address] = None,
    ):
        if not service.subnet_exists(subnet_id):
            raise HTTPException(status_code=404, detail="Subnet not found")
        if address_start is not None and address_end is not None and address_start > address_end:
            raise HTTPException(
                status_code=400,
                detail="address_start must be less than or equal to address_end",
            )
        return service.list_subnet_addresses(
            subnet_id,
            limit=limit,
            offset=offset,
            status=status,
            team=team,
            environment=environment,
            machine_type=machine_type,
            tag_id=tag_id,
            query=query,
            sort=sort,
            direction=direction,
            address_start=str(address_start) if address_start else None,
            address_end=str(address_end) if address_end else None,
        )


    @router.put("/api/ipam/subnets/{subnet_id}", response_model=SubnetSummary, dependencies=[Depends(require_ipam_permission("write"))])
    def update_subnet(subnet_id: int, req: SubnetRequest, user: Optional[Dict] = Depends(require_logged_in_user)):
        try:
            return service.update_subnet(subnet_id, req.cidr, req.vlan, req.description, user_id=user["id"] if user else None)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))


    @router.delete("/api/ipam/subnets/{subnet_id}", dependencies=[Depends(require_ipam_permission("write"))])
    def delete_subnet(subnet_id: int, user: Optional[Dict] = Depends(require_logged_in_user)):
        user_id = user["id"] if user else None
        deleted = service.delete_subnet(subnet_id, user_id=user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Subnet not found")
        return {"deleted": subnet_id}


    @router.post("/api/ipam/subnets/{subnet_id}/addresses", response_model=SubnetSummary, dependencies=[Depends(require_ipam_permission("write"))])
    def create_address(subnet_id: int, req: AddressRequest, user: Optional[Dict] = Depends(require_logged_in_user)):
        try:
            user_id = user["id"] if user else None
            return service.add_address(
                subnet_id, req.address, req.status, req.hostname, req.description,
                req.team, req.machineType, req.vmCluster, req.environment, req.locked,
                req.allocationType, user_id=user_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))


    @router.put("/api/ipam/subnets/{subnet_id}/addresses/{address_id}", response_model=SubnetSummary, dependencies=[Depends(require_ipam_permission("write"))])
    def edit_address(subnet_id: int, address_id: int, req: AddressRequest, user: Optional[Dict] = Depends(require_logged_in_user)):
        try:
            user_id = user["id"] if user else None
            return service.update_address(
                subnet_id, address_id, req.address, req.status, req.hostname, req.description,
                req.team, req.machineType, req.vmCluster, req.environment, req.locked,
                req.allocationType, user_id=user_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))


    @router.delete("/api/ipam/subnets/{subnet_id}/addresses/{address_id}", response_model=SubnetSummary, dependencies=[Depends(require_ipam_permission("write"))])
    def remove_address(subnet_id: int, address_id: int, user: Optional[Dict] = Depends(require_logged_in_user)):
        try:
            user_id = user["id"] if user else None
            return service.delete_address(subnet_id, address_id, user_id=user_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))


    @router.post(
        "/api/ipam/subnets/{subnet_id}/addresses/{address_id}/move",
        response_model=MoveAddressResponse,
        dependencies=[Depends(require_ipam_permission("write"))],
    )
    def move_ipam_address(subnet_id: int, address_id: int, req: MoveAddressRequest, user: Optional[Dict] = Depends(require_logged_in_user)):
        try:
            return service.move_address(subnet_id, address_id, req.targetSubnetId, user_id=user["id"] if user else None)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))


    @router.patch("/api/ipam/subnets/{subnet_id}/addresses/bulk", response_model=SubnetSummary, dependencies=[Depends(require_ipam_permission("write"))])
    def bulk_edit_addresses(subnet_id: int, req: BulkAddressUpdateRequest):
        if not req.addressIds:
            raise HTTPException(status_code=400, detail="No addresses selected")
        try:
            fields = req.model_dump(exclude_unset=True, exclude={"addressIds"})
            return service.bulk_update_addresses(subnet_id, req.addressIds, fields)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))


    @router.post("/api/ipam/subnets/{subnet_id}/addresses/bulk-delete", response_model=SubnetSummary, dependencies=[Depends(require_ipam_permission("write"))])
    def bulk_delete_addresses(subnet_id: int, req: BulkAddressDeleteRequest):
        if not req.addressIds:
            raise HTTPException(status_code=400, detail="No addresses selected")
        try:
            return service.bulk_delete_addresses(subnet_id, req.addressIds)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))


    @router.post(
        "/api/ipam/subnets/{subnet_id}/addresses/bulk-move",
        response_model=BulkMoveAddressesResponse,
        dependencies=[Depends(require_ipam_permission("scan"))],
    )
    def bulk_move_addresses(subnet_id: int, req: BulkMoveAddressesRequest, user: Optional[Dict] = Depends(require_logged_in_user)):
        if not req.addressIds:
            raise HTTPException(status_code=400, detail="No addresses selected")
        user_id = user["id"] if user else None
        try:
            return service.bulk_move_addresses(subnet_id, req.addressIds, req.targetSubnetId, user_id=user_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))


    @router.post("/api/ipam/subnets/{subnet_id}/addresses/{address_id}/rescan", response_model=SubnetSummary, dependencies=[Depends(require_ipam_permission("scan"))])
    async def rescan_address(subnet_id: int, address_id: int):
        return await scans.rescan_address(subnet_id, address_id)


    @router.get("/api/ipam/subnets/{subnet_id}/scan-excludes", response_model=List[ScanExcludeEntry], dependencies=[Depends(require_ipam_permission("admin"))])
    def list_subnet_scan_excludes(subnet_id: int):
        if not service.subnet_exists(subnet_id):
            raise HTTPException(status_code=404, detail="Subnet not found")
        return service.list_scan_excludes_detailed(subnet_id)


    @router.post("/api/ipam/subnets/{subnet_id}/scan-excludes", response_model=List[ScanExcludeEntry], dependencies=[Depends(require_ipam_permission("admin"))])
    def create_subnet_scan_exclude(subnet_id: int, req: ScanExcludeRequest):
        data = service.get_subnet(subnet_id)
        if data is None:
            raise HTTPException(status_code=404, detail="Subnet not found")
        try:
            service.validate_address_in_subnet(req.address, data["cidr"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        service.add_scan_exclude(subnet_id, req.address.strip())
        return service.list_scan_excludes_detailed(subnet_id)


    @router.delete("/api/ipam/subnets/{subnet_id}/scan-excludes/{exclude_id}", response_model=List[ScanExcludeEntry], dependencies=[Depends(require_ipam_permission("admin"))])
    def remove_subnet_scan_exclude(subnet_id: int, exclude_id: int):
        if not service.subnet_exists(subnet_id):
            raise HTTPException(status_code=404, detail="Subnet not found")
        service.remove_scan_exclude_by_id(subnet_id, exclude_id)
        return service.list_scan_excludes_detailed(subnet_id)


    @router.get("/api/ipam/subnets/{subnet_id}/range-reservations", response_model=List[RangeReservationResponse], dependencies=[Depends(require_ipam_permission("read"))])
    def list_range_reservations(subnet_id: int):
        if not service.subnet_exists(subnet_id):
            raise HTTPException(status_code=404, detail="Subnet not found")
        return service.get_range_reservations(subnet_id)


    @router.post("/api/ipam/subnets/{subnet_id}/range-reservations", response_model=RangeReservationResponse, dependencies=[Depends(require_ipam_permission("write"))])
    def create_range_reservation(subnet_id: int, req: RangeReservationRequest, user: Optional[Dict] = Depends(require_logged_in_user)):
        try:
            return service.add_range_reservation(subnet_id, req.start_ip, req.end_ip, req.allocation_type, req.status, req.label, req.description, user_id=user["id"] if user else None)
        except ValueError as exc:
            raise HTTPException(status_code=404 if str(exc) == "Subnet not found" else 400, detail=str(exc))


    @router.put("/api/ipam/subnets/{subnet_id}/range-reservations/{reservation_id}", response_model=RangeReservationResponse, dependencies=[Depends(require_ipam_permission("write"))])
    def update_range_reservation(subnet_id: int, reservation_id: int, req: RangeReservationRequest, user: Optional[Dict] = Depends(require_logged_in_user)):
        try:
            return service.update_range_reservation(subnet_id, reservation_id, req.start_ip, req.end_ip, req.allocation_type, req.status, req.label, req.description, user_id=user["id"] if user else None)
        except ValueError as exc:
            raise HTTPException(status_code=404 if str(exc) == "Range reservation not found" else 400, detail=str(exc))


    @router.delete("/api/ipam/subnets/{subnet_id}/range-reservations/{reservation_id}", dependencies=[Depends(require_ipam_permission("write"))])
    def delete_range_reservation(subnet_id: int, reservation_id: int, user: Optional[Dict] = Depends(require_logged_in_user)):
        if not service.subnet_exists(subnet_id):
            raise HTTPException(status_code=404, detail="Subnet not found")
        if not service.delete_range_reservation(subnet_id, reservation_id, user_id=user["id"] if user else None):
            raise HTTPException(status_code=404, detail="Range reservation not found")
        return {"deleted": reservation_id}


    @router.post("/api/ipam/subnets/{subnet_id}/dhcp-pools", response_model=DhcpPoolResponse, dependencies=[Depends(require_ipam_permission("write"))])
    def create_dhcp_pool(subnet_id: int, req: DhcpPoolCreate, user: Optional[Dict] = Depends(require_logged_in_user)):
        if service.get_subnet(subnet_id) is None:
            raise HTTPException(status_code=404, detail="Subnet not found")
        try:
            return service.add_dhcp_pool(subnet_id, req.start_ip, req.end_ip, req.name, req.description, user_id=user["id"] if user else None)

        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))


    @router.get("/api/ipam/subnets/{subnet_id}/dhcp-pools", response_model=List[DhcpPoolResponse], dependencies=[Depends(require_ipam_permission("read"))])
    def list_dhcp_pools(subnet_id: int):
        if not service.subnet_exists(subnet_id):
            raise HTTPException(status_code=404, detail="Subnet not found")
        return service.get_dhcp_pools(subnet_id)


    @router.delete("/api/ipam/subnets/{subnet_id}/dhcp-pools/{pool_id}", dependencies=[Depends(require_ipam_permission("write"))])
    def delete_dhcp_pool(subnet_id: int, pool_id: int, user: Optional[Dict] = Depends(require_logged_in_user)):
        if not service.subnet_exists(subnet_id):
            raise HTTPException(status_code=404, detail="Subnet not found")
        deleted = service.delete_dhcp_pool(subnet_id, pool_id, user_id=user["id"] if user else None)
        if not deleted:
            raise HTTPException(status_code=404, detail="DHCP pool not found")
        return {"deleted": pool_id}


    @router.put(
        "/api/ipam/subnets/{subnet_id}/dhcp-pools/{pool_id}",
        response_model=DhcpPoolResponse,
        dependencies=[Depends(require_ipam_permission("write"))],
    )
    def update_dhcp_pool(subnet_id: int, pool_id: int, req: DhcpPoolCreate, user: Optional[Dict] = Depends(require_logged_in_user)):
        if not service.subnet_exists(subnet_id):
            raise HTTPException(status_code=404, detail="Subnet not found")
        try:
            return service.update_dhcp_pool(subnet_id, pool_id, req.start_ip, req.end_ip, req.name, req.description, user_id=user["id"] if user else None)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))


    @router.post(
        "/api/ipam/subnets/{subnet_id}/dhcp-pools/{pool_id}/move",
        dependencies=[Depends(require_ipam_permission("write"))],
    )
    def move_dhcp_pool(subnet_id: int, pool_id: int, req: MoveAddressRequest, user: Optional[Dict] = Depends(require_logged_in_user)):
        try:
            return service.move_dhcp_pool(subnet_id, pool_id, req.targetSubnetId, user_id=user["id"] if user else None)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))


    @router.post(
        "/api/ipam/dhcp-pools/bulk-move",
        response_model=BulkMoveDhcpPoolsResponse,
        dependencies=[Depends(require_ipam_permission("write"))],
    )
    def bulk_move_dhcp_pools(req: BulkMoveDhcpPoolsRequest, user: Optional[Dict] = Depends(require_logged_in_user)):
        try:
            return service.bulk_move_dhcp_pools(req.poolIds, req.targetSubnetId, user_id=user["id"] if user else None)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))


    @router.get("/api/ipam/tags", response_model=TagListResponse, dependencies=[Depends(require_ipam_permission("read"))])
    def get_tags():
        tags = service.get_tags()
        return TagListResponse(tags=tags, count=len(tags))


    @router.post("/api/ipam/tags", response_model=TagResponse, dependencies=[Depends(require_ipam_permission("admin"))])
    def create_tag(req: TagCreateRequest, user: Optional[Dict] = Depends(require_logged_in_user)):
        try:
            return service.create_tag(req.name, req.description, req.color, user_id=user["id"] if user else None)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail=f'Tag "{req.name}" already exists')


    @router.delete("/api/ipam/tags/{tag_id}", dependencies=[Depends(require_ipam_permission("admin"))])
    def delete_tag(tag_id: int, user: Optional[Dict] = Depends(require_logged_in_user)):
        deleted = service.delete_tag(tag_id, user_id=user["id"] if user else None)
        if not deleted:
            raise HTTPException(status_code=404, detail="Tag not found")
        return {"deleted": tag_id}


    @router.get("/api/ipam/tags/search", response_model=List[TagSummary], dependencies=[Depends(require_ipam_permission("read"))])
    def search_tags(q: str = ""):
        if not q or not q.strip():
            return []
        return service.search_tags(q.strip())


    @router.get("/api/ipam/subnets/{subnet_id}/tags", response_model=List[TagSummary], dependencies=[Depends(require_ipam_permission("read"))])
    def get_subnet_tags(subnet_id: int):
        if not service.subnet_exists(subnet_id):
            raise HTTPException(status_code=404, detail="Subnet not found")
        return service.get_subnet_tags(subnet_id)


    @router.post("/api/ipam/subnets/{subnet_id}/tags/{tag_id}", response_model=List[TagSummary], dependencies=[Depends(require_ipam_permission("write"))])
    def add_subnet_tag(subnet_id: int, tag_id: int, user: Optional[Dict] = Depends(require_logged_in_user)):
        if not service.subnet_exists(subnet_id):
            raise HTTPException(status_code=404, detail="Subnet not found")
        try:
            service.add_subnet_tag(subnet_id, tag_id, user_id=user["id"] if user else None)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return service.get_subnet_tags(subnet_id)


    @router.delete("/api/ipam/subnets/{subnet_id}/tags/{tag_id}", response_model=List[TagSummary], dependencies=[Depends(require_ipam_permission("write"))])
    def remove_subnet_tag(subnet_id: int, tag_id: int, user: Optional[Dict] = Depends(require_logged_in_user)):
        if not service.subnet_exists(subnet_id):
            raise HTTPException(status_code=404, detail="Subnet not found")
        service.remove_subnet_tag(subnet_id, tag_id, user_id=user["id"] if user else None)
        return service.get_subnet_tags(subnet_id)


    @router.get("/api/ipam/addresses/{address_id}/tags", response_model=List[TagSummary], dependencies=[Depends(require_ipam_permission("read"))])
    def get_address_tags(address_id: int):
        return service.get_address_tags(address_id)


    @router.post("/api/ipam/addresses/{address_id}/tags/{tag_id}", response_model=List[TagSummary], dependencies=[Depends(require_ipam_permission("write"))])
    def add_address_tag(address_id: int, tag_id: int, user: Optional[Dict] = Depends(require_logged_in_user)):
        try:
            service.add_address_tag(address_id, tag_id, user_id=user["id"] if user else None)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return service.get_address_tags(address_id)


    @router.delete("/api/ipam/addresses/{address_id}/tags/{tag_id}", response_model=List[TagSummary], dependencies=[Depends(require_ipam_permission("write"))])
    def remove_address_tag(address_id: int, tag_id: int, user: Optional[Dict] = Depends(require_logged_in_user)):
        service.remove_address_tag(address_id, tag_id, user_id=user["id"] if user else None)
        return service.get_address_tags(address_id)


    @router.get("/api/ipam/tags/{tag_id}/subnets", response_model=List[SubnetSummary], dependencies=[Depends(require_ipam_permission("read"))])
    def get_subnets_by_tag(tag_id: int):
        try:
            return service.get_subnets_by_tag(tag_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))


    @router.get("/api/ipam/tags/{tag_id}/addresses", response_model=List[SearchAddressEntry], dependencies=[Depends(require_ipam_permission("read"))])
    def get_addresses_by_tag(tag_id: int):
        try:
            return service.get_addresses_by_tag(tag_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))


    @router.post("/api/ipam/allocation-plan", response_model=AllocationPlanResponse, dependencies=[Depends(require_ipam_permission("read"))])
    def get_allocation_plan(req: AllocationPlanRequest):
        try:
            return service.get_allocation_plan(req.parent, req.prefix)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))


    @router.get("/api/ipam/subnet-allocation", response_model=SubnetAllocationResponse, dependencies=[Depends(require_ipam_permission("read"))])
    def get_subnet_allocation(parent: str, prefix: int):
        try:
            return service.find_next_contiguous_subnet(parent, prefix)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))


    @router.get("/api/ipam/audit", response_model=AuditLogPage, dependencies=[Depends(require_ipam_permission("read"))])
    def query_audit_log(
        subnet_id: Optional[int] = None,
        address_id: Optional[int] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        change_type: Optional[List[str]] = Query(default=None),
        change_types: Optional[List[str]] = Query(default=None),
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ):
        start, end, selected_types = _audit_filters(
            start_time, end_time, start_date, end_date, change_type, change_types
        )
        return service.query_audit_log(
            subnet_id=subnet_id,
            address_id=address_id,
            start_time=start,
            end_time=end,
            change_types=selected_types,
            limit=limit,
            offset=offset,
        )


    @router.get("/api/ipam/audit/address/{address_id}", response_model=List[AuditLogEntry], dependencies=[Depends(require_ipam_permission("read"))])
    def get_address_audit_log(address_id: int, limit: int = Query(default=100, ge=1, le=100), offset: int = Query(default=0, ge=0)):
        return service.get_address_audit_log(address_id, limit=limit, offset=offset)


    @router.get("/api/ipam/audit/subnet/{subnet_id}", response_model=List[AuditLogEntry], dependencies=[Depends(require_ipam_permission("read"))])
    def get_subnet_audit_log(
        subnet_id: int,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = Query(default=50, ge=1, le=100),
    ):
        return service.get_subnet_audit_log(subnet_id, start_time=start_time, end_time=end_time, limit=limit)


    @router.get("/api/ipam/audit/export", response_model=List[AuditLogEntry], deprecated=True, dependencies=[Depends(require_ipam_permission("admin"))])
    def export_audit_log_legacy(
        subnet_id: Optional[int] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = Query(default=1000, ge=1, le=1000),
    ):
        rows = service.export_audit_log_csv(
            subnet_id=subnet_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
        result = []
        for r in rows:
            entry = AuditLogEntry(
                id=r["id"],
                addressId=r["address_id"],
                subnetId=r["subnet_id"],
                userId=r["user_id"],
                changeType=r["change_type"],
                oldValue=json.loads(r["old_value"]) if r["old_value"] else None,
                newValue=json.loads(r["new_value"]) if r["new_value"] else None,
                description=r["description"],
                ipAddress=r["ip_address"],
                subnetCidr=r["subnet_cidr"],
                createdAt=r["created_at"],
            )
            if r["user_id"]:
                user = service.get_user_by_id(r["user_id"])
                entry.username = user["username"] if user else None
            result.append(entry)
        return result


    def audit_csv_filters(
        start_time: Optional[str],
        end_time: Optional[str],
        start_date: Optional[str],
        end_date: Optional[str],
        change_type: Optional[List[str]],
        change_types: Optional[List[str]],
    ):
        start, end, selected_types = _audit_filters(
            start_time, end_time, start_date, end_date, change_type, change_types
        )
        return {"start_time": start, "end_time": end, "change_types": selected_types}

    @router.get("/api/ipam/audit/export.csv", dependencies=[Depends(require_ipam_permission("admin"))])
    @router.get("/api/ipam/audit.csv", include_in_schema=False, dependencies=[Depends(require_ipam_permission("admin"))])
    def export_audit_log_csv(
        subnet_id: Optional[int] = None,
        address_id: Optional[int] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        change_type: Optional[List[str]] = Query(default=None),
        change_types: Optional[List[str]] = Query(default=None),
    ):
        filters = audit_csv_filters(start_time, end_time, start_date, end_date, change_type, change_types)
        return _audit_csv_response(
            service, subnet_id=subnet_id, address_id=address_id, **filters
        )

    @router.get("/api/ipam/audit/subnet/{subnet_id}/export.csv", dependencies=[Depends(require_ipam_permission("read"))])
    def export_subnet_audit_log_csv(
        subnet_id: int,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        change_type: Optional[List[str]] = Query(default=None),
        change_types: Optional[List[str]] = Query(default=None),
    ):
        filters = audit_csv_filters(start_time, end_time, start_date, end_date, change_type, change_types)
        return _audit_csv_response(service, subnet_id=subnet_id, **filters)

    @router.get("/api/ipam/audit/address/{address_id}/export.csv", dependencies=[Depends(require_ipam_permission("read"))])
    def export_address_audit_log_csv(
        address_id: int,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        change_type: Optional[List[str]] = Query(default=None),
        change_types: Optional[List[str]] = Query(default=None),
    ):
        filters = audit_csv_filters(start_time, end_time, start_date, end_date, change_type, change_types)
        return _audit_csv_response(service, address_id=address_id, **filters)


    @router.post("/api/ipam/subnets/{subnet_id}/autodiscover", response_model=AutodiscoverResponse, dependencies=[Depends(require_ipam_permission("scan"))])
    async def autodiscover_subnet(subnet_id: int):
        return await scans.autodiscover_subnet(subnet_id)


    @router.post("/api/ipam/subnets/{subnet_id}/autodiscover/start", dependencies=[Depends(require_ipam_permission("scan"))])
    async def start_autodiscover_job(subnet_id: int):
        return await scans.start_autodiscover_job(subnet_id)


    @router.post("/api/ipam/subnets/{subnet_id}/autodiscover/jobs/{job_id}/cancel", dependencies=[Depends(require_ipam_permission("scan"))])
    def cancel_autodiscover_job(subnet_id: int, job_id: str):
        return scans.cancel_autodiscover_job(subnet_id, job_id)


    @router.post("/api/ipam/subnets/{subnet_id}/autodiscover/jobs/{job_id}/retry", dependencies=[Depends(require_ipam_permission("scan"))])
    async def retry_autodiscover_job(subnet_id: int, job_id: str):
        return await scans.retry_autodiscover_job(subnet_id, job_id)


    @router.get("/api/ipam/subnets/{subnet_id}/scan-schedule", dependencies=[Depends(require_ipam_permission("read"))])
    def get_scan_schedule(subnet_id: int):
        return scans.get_scan_schedule(subnet_id)


    @router.put("/api/ipam/subnets/{subnet_id}/scan-schedule", dependencies=[Depends(require_ipam_permission("admin"))])
    def update_scan_schedule(subnet_id: int, req: ScanScheduleRequest):
        return scans.update_scan_schedule(subnet_id, req)


    @router.get("/api/ipam/subnets/{subnet_id}/autodiscover/active", dependencies=[Depends(require_ipam_permission("scan"))])
    def get_active_scan(subnet_id: int):
        return scans.get_active_scan(subnet_id)


    @router.get("/api/ipam/subnets/{subnet_id}/autodiscover/jobs/{job_id}", dependencies=[Depends(require_ipam_permission("scan"))])
    def get_autodiscover_job(subnet_id: int, job_id: str):
        return scans.get_autodiscover_job(subnet_id, job_id)


    @router.get("/api/ipam/subnets/{subnet_id}/autodiscover/stream/{job_id}", dependencies=[Depends(require_ipam_permission("scan"))])
    async def stream_autodiscover_job(subnet_id: int, job_id: str):
        return await scans.stream_autodiscover_job(subnet_id, job_id)


    @router.get("/api/ipam/subnets/{subnet_id}/scans", response_model=List[ScanSummary], dependencies=[Depends(require_ipam_permission("read"))])
    def get_subnet_scans(subnet_id: int):
        return scans.get_subnet_scans(subnet_id)


    return router
