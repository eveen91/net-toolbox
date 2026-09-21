import ipaddress
import re
from typing import Annotated, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

SCAN_CONCURRENCY_MIN = 1
SCAN_CONCURRENCY_MAX = 256
HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9.\-]+$")


class SubnetRequest(BaseModel):
    cidr: str = Field(min_length=3, max_length=18)
    vlan: Optional[int] = Field(default=None, ge=1, le=4094)
    description: Optional[str] = Field(default=None, max_length=500)

    @field_validator("cidr")
    @classmethod
    def validate_ipv4_cidr(cls, value: str) -> str:
        try:
            network = ipaddress.ip_network(value.strip(), strict=False)
        except ValueError:
            raise ValueError("CIDR must be a valid IPv4 network")
        if network.version != 4:
            raise ValueError("IPAM currently supports IPv4 CIDR networks only")
        return str(network)

    @field_validator("description")
    @classmethod
    def normalize_optional_text(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() or None if value is not None else None


class SubnetSummary(BaseModel):
    id: int
    cidr: str
    vlan: Optional[int] = None
    parentId: Optional[int] = None
    description: Optional[str] = None
    updatedAt: str
    totalAddresses: int
    usedCount: int
    freeCount: int
    reservedCount: int
    recordedCount: int


class AddressEntry(BaseModel):
    id: int
    address: str
    status: Literal["used", "free", "reserved"]
    hostname: Optional[str] = None
    description: Optional[str] = None
    team: Optional[str] = None
    machineType: Optional[Literal["physical", "vm"]] = None
    vmCluster: Optional[str] = None
    environment: Optional[Literal["prod", "test", "dev"]] = None
    locked: bool = False
    updatedAt: str


class AddressPageResponse(BaseModel):
    addresses: List[AddressEntry]
    total: int
    limit: int
    offset: int


class SearchAddressEntry(AddressEntry):
    subnetId: int
    subnetCidr: str
    subnetVlan: Optional[int] = None


class IpamSettingsResponse(BaseModel):
    scanConcurrencyLimit: int
    scanConcurrencyMin: int
    scanConcurrencyMax: int


class UpdateIpamSettingsRequest(BaseModel):
    scanConcurrencyLimit: int = Field(ge=SCAN_CONCURRENCY_MIN, le=SCAN_CONCURRENCY_MAX)


class AddressRequest(BaseModel):
    address: str = Field(min_length=7, max_length=15)
    status: Literal["used", "free", "reserved"] = "used"
    allocationType: Literal["gateway", "static", "dhcp", "vip", "loopback", "infrastructure", "network", "broadcast"] = "static"
    hostname: Optional[str] = Field(default=None, max_length=253)
    description: Optional[str] = Field(default=None, max_length=500)
    team: Optional[str] = Field(default=None, max_length=100)
    machineType: Optional[Literal["physical", "vm"]] = None
    vmCluster: Optional[str] = Field(default=None, max_length=100)
    environment: Optional[Literal["prod", "test", "dev"]] = None
    locked: bool = False

    @field_validator("address")
    @classmethod
    def validate_ipv4_address(cls, value: str) -> str:
        try:
            address = ipaddress.IPv4Address(value.strip())
        except ipaddress.AddressValueError:
            raise ValueError("Address must be a valid IPv4 address")
        return str(address)

    @field_validator("hostname", "description", "team", "vmCluster")
    @classmethod
    def normalize_optional_text(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() or None if value is not None else None

    @field_validator("hostname")
    @classmethod
    def validate_hostname(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not HOSTNAME_RE.fullmatch(value):
            raise ValueError("Hostname may contain only letters, numbers, dots, and hyphens")
        return value


class BulkAddressUpdateRequest(BaseModel):
    """
    Bulk-edit a set of addresses (by id) within one subnet.

    Every field below besides addressIds is optional so a request only
    touches what it explicitly sends. This depends on Pydantic v2's
    exclude_unset behavior: a field key that's simply absent from the
    request body never lands in `model_fields_set`, while a field sent
    as `null` DOES land in `model_fields_set` (with a value of None) -
    so `req.model_dump(exclude_unset=True)` distinguishes "leave this
    field alone" (key absent) from "clear this field" (key present,
    value null) from "set this field" (key present, real value).
    Do NOT special-case any of these fields with `is not None` checks
    downstream - that collapses "not sent" and "explicitly cleared"
    into the same branch, which is exactly what this model exists to
    avoid.
    """

    addressIds: Annotated[List[Annotated[int, Field(gt=0)]], Field(min_length=1, max_length=1000)]
    status: Optional[Literal["used", "free", "reserved"]] = None
    team: Optional[str] = Field(default=None, max_length=100)
    machineType: Optional[Literal["physical", "vm"]] = None
    vmCluster: Optional[str] = Field(default=None, max_length=100)
    environment: Optional[Literal["prod", "test", "dev"]] = None
    locked: Optional[bool] = None

    @field_validator("team", "vmCluster")
    @classmethod
    def normalize_optional_text(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() or None if value is not None else None


class BulkAddressDeleteRequest(BaseModel):
    addressIds: Annotated[List[Annotated[int, Field(gt=0)]], Field(min_length=1, max_length=1000)]


class BulkMoveAddressesRequest(BaseModel):
    addressIds: Annotated[List[Annotated[int, Field(gt=0)]], Field(min_length=1, max_length=1000)]
    targetSubnetId: int = Field(gt=0)


class BulkMoveSkippedEntry(BaseModel):
    addressId: int
    address: Optional[str] = None
    reason: str


class BulkMoveAddressesResponse(BaseModel):
    fromSubnet: SubnetSummary
    toSubnet: SubnetSummary
    movedCount: int
    skipped: List[BulkMoveSkippedEntry] = []


class DhcpPoolCreate(BaseModel):
    start_ip: str = Field(min_length=7, max_length=15)
    end_ip: str = Field(min_length=7, max_length=15)
    name: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)

    @field_validator("start_ip", "end_ip")
    @classmethod
    def validate_ipv4_address(cls, value: str) -> str:
        try:
            return str(ipaddress.IPv4Address(value.strip()))
        except ipaddress.AddressValueError:
            raise ValueError("DHCP pool addresses must be valid IPv4 addresses")


class RangeReservationRequest(BaseModel):
    start_ip: str = Field(min_length=7, max_length=15)
    end_ip: str = Field(min_length=7, max_length=15)
    allocation_type: Literal["reserved_range"] = "reserved_range"
    status: Literal["active", "released"] = "active"
    label: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)

    @field_validator("start_ip", "end_ip")
    @classmethod
    def validate_ipv4_address(cls, value: str) -> str:
        try:
            return str(ipaddress.IPv4Address(value.strip()))
        except ipaddress.AddressValueError:
            raise ValueError("Range reservation addresses must be valid IPv4 addresses")


class RangeReservationResponse(BaseModel):
    id: int
    subnet_id: int
    start_ip: str
    end_ip: str
    allocation_type: Literal["reserved_range"]
    status: Literal["active", "released"]
    label: Optional[str] = None
    description: Optional[str] = None
    created_at: str
    updated_at: str


class BulkMoveDhcpPoolsRequest(BaseModel):
    poolIds: Annotated[List[Annotated[int, Field(gt=0)]], Field(min_length=1, max_length=1000)]
    targetSubnetId: int = Field(gt=0)


class BulkMoveDhcpPoolsResponse(BaseModel):
    movedCount: int


class DhcpPoolResponse(BaseModel):
    id: int
    subnet_id: int
    start_ip: str
    end_ip: str
    name: Optional[str] = None
    description: Optional[str] = None
    updated_at: str


class ScanExcludeEntry(BaseModel):
    id: int
    address: str


class ScanExcludeRequest(BaseModel):
    address: str = Field(min_length=7, max_length=15)

    @field_validator("address")
    @classmethod
    def validate_ipv4_address(cls, value: str) -> str:
        try:
            return str(ipaddress.IPv4Address(value.strip()))
        except ipaddress.AddressValueError:
            raise ValueError("Scan exclusion must be a valid IPv4 address")


class ScanScheduleRequest(BaseModel):
    intervalMinutes: int = Field(ge=1, le=10080)
    enabled: bool = True


class AutodiscoverResult(BaseModel):
    address: str
    alive: bool
    hostname: Optional[str] = None


class HostnameChange(BaseModel):
    address: str
    oldHostname: Optional[str] = None
    newHostname: Optional[str] = None


class ScanDiff(BaseModel):
    newlyUsed: List[str]
    wentQuiet: List[str]
    hostnameChanged: List[HostnameChange]


class AutodiscoverResponse(BaseModel):
    scanId: int
    scannedCount: int
    usedCount: int
    freeCount: int
    skippedCount: int
    results: List[AutodiscoverResult]
    diff: ScanDiff


class ScanSummary(BaseModel):
    id: int
    subnet_id: int
    startedAt: str
    finishedAt: str
    scannedCount: int
    usedCount: int
    freeCount: int
    skippedCount: int
    newlyUsedCount: int
    wentQuietCount: int
    hostnameChangedCount: int
    diff: ScanDiff


class DashboardEntry(BaseModel):
    id: int
    cidr: str
    vlan: Optional[int] = None
    description: Optional[str] = None
    totalAddresses: int
    usedCount: int
    freeCount: int
    reservedCount: int
    recordedCount: int
    lastScannedAt: Optional[str] = None
    lastScanNewlyUsed: Optional[int] = None
    lastScanWentQuiet: Optional[int] = None
    lastScanHostnameChanged: Optional[int] = None


class MisplacedAddressEntry(BaseModel):
    addressId: int
    address: str
    status: str
    hostname: Optional[str] = None
    currentSubnetId: int
    currentSubnetCidr: str
    proposedSubnetId: int
    proposedSubnetCidr: str


class MisplacedDhcpPoolEntry(BaseModel):
    poolId: int
    startIp: str
    endIp: str
    name: Optional[str] = None
    description: Optional[str] = None
    currentSubnetId: int
    currentSubnetCidr: str
    proposedSubnetId: int
    proposedSubnetCidr: str


class MoveAddressRequest(BaseModel):
    targetSubnetId: int


class MoveAddressResponse(BaseModel):
    fromSubnet: SubnetSummary
    toSubnet: SubnetSummary


class TagCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    color: Optional[str] = "#6366f1"

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        v = v.strip()
        import re
        if not v or len(v) > 50:
            raise ValueError("Tag name must be 2-50 characters")
        if not re.match(r'^[a-zA-Z0-9_-]{2,50}$', v):
            raise ValueError("Tag name must be alphanumeric, hyphens, and underscores only")
        return v

    @field_validator("color")
    @classmethod
    def validate_color(cls, v):
        if v is None:
            return "#6366f1"
        v = v.strip()
        if not re.match(r'^#[0-9a-fA-F]{6}$', v):
            raise ValueError("Color must be a hex value (e.g. #6366f1)")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v):
        if v is not None and len(v) > 200:
            raise ValueError("Description must be at most 200 characters")
        return v


class TagResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    color: str
    createdAt: str
    updatedAt: str


class TagListResponse(BaseModel):
    tags: List[TagResponse]
    count: int


class TagSummary(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    color: str


class NextAvailableIpResponse(BaseModel):
    subnetId: int
    nextAvailableIp: Optional[str] = None


class AllocateNextAddressRequest(BaseModel):
    status: Literal["used", "reserved"] = "reserved"
    hostname: Optional[str] = Field(default=None, max_length=253)
    description: Optional[str] = Field(default=None, max_length=500)
    team: Optional[str] = Field(default=None, max_length=100)
    machineType: Optional[Literal["physical", "vm"]] = None
    vmCluster: Optional[str] = Field(default=None, max_length=100)
    environment: Optional[Literal["prod", "test", "dev"]] = None
    locked: bool = False

    @field_validator("hostname", "description", "team", "vmCluster")
    @classmethod
    def normalize_optional_text(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() or None if value is not None else None

    @field_validator("hostname")
    @classmethod
    def validate_hostname(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not HOSTNAME_RE.fullmatch(value):
            raise ValueError("Hostname may contain only letters, numbers, dots, and hyphens")
        return value


class AllocateNextAddressResponse(BaseModel):
    address: AddressEntry
    subnet: SubnetSummary


class SubnetAllocationResponse(BaseModel):
    parent: str
    requestedPrefix: int
    recommendation: Optional[str] = None
    availableFrom: Optional[str] = None
    availableTo: Optional[str] = None
    totalAddresses: int = 0
    nextAvailableAfter: Optional[str] = None


class AllocationPlanRequest(BaseModel):
    parent: str = Field(min_length=3, max_length=18)
    prefix: int = Field(ge=0, le=32)

    @field_validator("parent")
    @classmethod
    def validate_parent(cls, value: str) -> str:
        return SubnetRequest.validate_ipv4_cidr(value)


class AllocationRange(BaseModel):
    start: str
    end: str
    source: Literal["subnet", "address", "dhcp_pool"]
    cidr: Optional[str] = None


class AllocationPlanResponse(BaseModel):
    parent: str
    requestedPrefix: int
    recommendations: List[str]
    occupiedRanges: List[AllocationRange]
    freshnessToken: str
    totalAddresses: int


class CreateAllocatedSubnetRequest(SubnetRequest):
    parent: str = Field(min_length=3, max_length=18)
    freshnessToken: str = Field(min_length=16, max_length=256)
    tagIds: List[int] = Field(default_factory=list)

    @field_validator("parent")
    @classmethod
    def validate_parent(cls, value: str) -> str:
        return SubnetRequest.validate_ipv4_cidr(value)

    @field_validator("tagIds")
    @classmethod
    def validate_tag_ids(cls, value: List[int]) -> List[int]:
        if any(tag_id <= 0 for tag_id in value):
            raise ValueError("Tag IDs must be positive")
        if len(set(value)) != len(value):
            raise ValueError("Tag IDs must be unique")
        return value


class AuditLogEntry(BaseModel):
    id: int
    addressId: Optional[int] = None
    subnetId: Optional[int] = None
    dhcpPoolId: Optional[int] = None
    userId: Optional[int] = None
    username: Optional[str] = None
    changeType: str
    oldValue: Optional[Dict] = None
    newValue: Optional[Dict] = None
    description: Optional[str] = None
    ipAddress: Optional[str] = None
    subnetCidr: Optional[str] = None
    createdAt: str


class AuditLogPage(BaseModel):
    entries: List[AuditLogEntry]
    total: int
    limit: int
    offset: int
