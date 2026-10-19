from typing import Literal
from ipaddress import ip_address, ip_interface
from .naming import PortNaming
from .vlans import normalize_trunk
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Family = Literal['ethernet', 'sfp', 'qsfp', 'sas']
DeviceType = Literal['switch', 'router', 'firewall', 'server', 'storage', 'storage-shelf', 'cable-management']
Vendor = Literal['checkpoint', 'fortigate', 'generic']
SPEEDS = {'ethernet': (1, 10), 'sfp': (10, 25), 'qsfp': (40, 100), 'sas': (12,)}
COUNTS = {'ethernet': 96, 'sfp': 48, 'qsfp': 16, 'sas': 16}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class PortGroup(StrictModel):
    family: Family
    count: int = Field(strict=True, ge=0, le=96)
    speedGbps: int = Field(strict=True)

    @model_validator(mode='after')
    def domain(self):
        if self.count > COUNTS[self.family] or self.speedGbps not in SPEEDS[self.family]:
            raise ValueError('Invalid connector count or speed for this family')
        return self


class NetworkCard(PortGroup):
    controller: Literal['A', 'B'] | None = None
    id: int | None = Field(default=None, strict=True, ge=1)
    slotNumber: int = Field(strict=True, ge=1, le=16)
    name: str | None = Field(default=None, max_length=60)
    count: int = Field(strict=True, ge=1, le=8)

    @field_validator('name', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() or None if isinstance(value, str) else value


class DeviceConfig(StrictModel):
    driveBayCount: int | None = Field(default=None, strict=True, ge=0, le=120)
    occupiedBays: list[int] | None = Field(default=None, max_length=120)
    expansionPortCount: int | None = Field(default=None, strict=True, ge=0, le=16)

    @field_validator('occupiedBays', mode='before')
    @classmethod
    def occupied_numbers(cls, value):
        if value is not None and (not isinstance(value, list) or any(type(n) is not int or n < 1 or n > 120 for n in value) or len(value) != len(set(value))):
            raise ValueError('Occupied bays must be unique bay numbers from 1 to 120')
        return sorted(value) if value is not None else None

    heightU: int | None = Field(default=None,strict=True,ge=1,le=100)
    rackId: int | None = Field(default=None,strict=True,ge=1)
    rackPosition: int | None = Field(default=None,strict=True,ge=1,le=100)
    deviceType: DeviceType
    vendor: Vendor | None = None
    name: str = Field(min_length=1, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    managementPort: bool = Field(default=False, strict=True)
    portNaming: PortNaming = 'family'
    portUnit: int = Field(default=1, strict=True, ge=1, le=16)
    portSlot: int = Field(default=1, strict=True, ge=0, le=16)
    portGroups: list[PortGroup] | None = Field(default=None, max_length=3)
    networkCards: list[NetworkCard] | None = Field(default=None, min_length=1, max_length=16)

    @field_validator('name', 'model', 'description', mode='before')
    @classmethod
    def trim(cls, value, info):
        if isinstance(value, str):
            return value.strip() if info.field_name == 'name' else value.strip() or None
        return value

    @model_validator(mode='after')
    def domain(self):
        if self.deviceType not in ('storage', 'storage-shelf') and (self.driveBayCount or self.occupiedBays or self.expansionPortCount):
            raise ValueError('Drive bays and expansion ports are only available for storage heads and shelves')
        if self.driveBayCount is not None and any(n > self.driveBayCount for n in self.occupiedBays or []):
            raise ValueError('Occupied bay number exceeds the configured bay count')
        if self.deviceType == 'storage-shelf':
            if self.managementPort or self.networkCards or self.portGroups or self.expansionPortCount not in (None, 2):
                raise ValueError('Storage shelves have exactly two expansion ports and no network cards or management ports')
        if self.deviceType != 'switch' and (self.portNaming != 'family' or self.portUnit != 1 or self.portSlot != 1):
            raise ValueError('Custom port naming is only supported for switches')
        if self.deviceType == 'firewall':
            if self.vendor is None:
                raise ValueError('Choose a firewall vendor')
        elif self.vendor is not None:
            raise ValueError('Vendor is only supported for firewalls')
        if self.deviceType == 'cable-management':
            if self.heightU != 1 or self.managementPort or self.portGroups or self.networkCards:
                raise ValueError('Cable management panels occupy exactly 1U and have no network ports')
            return self
        if self.deviceType == 'storage-shelf':
            return self
        if self.deviceType in ('server', 'storage'):
            if any(card.family == 'sas' for card in self.networkCards or []):
                raise ValueError('Use dedicated expansion ports for SAS connections')
            if not self.networkCards or 'portGroups' in self.model_fields_set:
                raise ValueError('Servers/storage require networkCards and do not accept portGroups')
            if len({(card.controller,card.slotNumber) for card in self.networkCards}) != len(self.networkCards):
                raise ValueError('Network card slots must be unique')
            if self.deviceType == 'storage':
                if {card.controller for card in self.networkCards} != {'A','B'} or any(card.slotNumber > 8 for card in self.networkCards):
                    raise ValueError('Storage requires controllers A and B, each with NIC slots 1–8')
            elif any(card.controller is not None for card in self.networkCards):
                raise ValueError('Controller ownership is only supported for storage')
            ids = [card.id for card in self.networkCards if card.id is not None]
            if len(set(ids)) != len(ids):
                raise ValueError('Network card IDs must be unique')
            groups = self.networkCards
        else:
            if self.portGroups is None or 'networkCards' in self.model_fields_set:
                raise ValueError('Switches/firewalls require portGroups and do not accept networkCards')
            if len(self.portGroups) != 3 or {g.family for g in self.portGroups} != {'ethernet','sfp','qsfp'}:
                raise ValueError('Provide exactly one Ethernet, SFP and QSFP group')
            if self.deviceType == 'firewall' and any(g.family == 'sfp' and g.count > 32 for g in self.portGroups):
                raise ValueError('Firewalls support at most 32 SFP ports')
            groups = self.portGroups
        if not 1 <= sum(g.count for g in groups) <= 128:
            raise ValueError('Total socket count must be from 1 to 128')
        return self


class DeviceCreate(DeviceConfig):
    @model_validator(mode='after')
    def new_ids(self):
        if self.networkCards and any(card.id is not None for card in self.networkCards):
            raise ValueError('New cards must have null IDs')
        return self


class DeviceUpdate(DeviceConfig):
    expectedVersion: int = Field(strict=True, ge=1)
    confirmPortDataRemoval: bool = Field(default=False, strict=True)


class PortNetworkConfig(BaseModel):
    transceiver: Literal['sfp-1g','sfp-10g','sfp28-25g','rj45-1g'] | None = None
    ipAddress: str | None = Field(default=None, max_length=64)

    @field_validator('ipAddress', mode='before')
    @classmethod
    def normalize_ip(cls, value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError('Enter an IPv4 or IPv6 address, optionally with a prefix')
        value = value.strip()
        if not value:
            return None
        if '%' in value:
            raise ValueError('Scoped addresses are not supported; enter the address without a zone')
        try:
            return str(ip_interface(value) if '/' in value else ip_address(value))
        except ValueError as exc:
            raise ValueError('Enter a valid IPv4 or IPv6 address, optionally with a prefix (e.g. 192.0.2.1/24)') from exc

    portMode: Literal['access', 'trunk'] | None = None
    accessVlan: int | None = Field(default=None, strict=True, ge=1, le=4094)
    trunkVlans: str | None = Field(default=None, max_length=2000)
    nativeVlan: int | None = Field(default=None, strict=True, ge=1, le=4094)

    _trunk = field_validator('trunkVlans', mode='before')(normalize_trunk)

    @model_validator(mode='after')
    def vlan_domain(self):
        if self.portMode == 'access':
            if self.accessVlan is None or self.trunkVlans is not None or self.nativeVlan is not None:
                raise ValueError('Access requires one VLAN and no trunk/native settings')
        elif self.portMode == 'trunk':
            if self.trunkVlans is None or self.accessVlan is not None:
                raise ValueError('Trunk requires allowed VLANs and no access VLAN')
        elif any(v is not None for v in (self.accessVlan, self.trunkVlans, self.nativeVlan)):
            raise ValueError('Choose access or trunk before assigning VLANs')
        return self


class PortAssignment(PortNetworkConfig, StrictModel):
    targetPortId: int | None = Field(default=None,strict=True,ge=1)
    targetVersion: int | None = Field(default=None,strict=True,ge=1)
    replacementToken: str | None = Field(default=None,min_length=64,max_length=64)

    @model_validator(mode='after')
    def linked_target(self):
        if self.targetPortId is not None and self.targetVersion is None:
            raise ValueError('Choose the destination device version with the target port')
        if self.targetPortId is None and (self.targetVersion is not None or self.replacementToken is not None):
            raise ValueError('Choose a target port before confirming a connection change')
        return self

    label: str | None = Field(max_length=50)
    leadsTo: str | None = Field(max_length=200)
    expectedVersion: int = Field(strict=True, ge=1)

    @field_validator('label', 'leadsTo', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() or None if isinstance(value, str) else value


class DeviceDelete(StrictModel):
    expectedVersion: int = Field(strict=True, ge=1)
    confirmDelete: bool = Field(default=False, strict=True)


class DeviceSummary(BaseModel):
    driveBayCount: int
    occupiedBays: list[int]
    expansionPortCount: int
    heightU: int | None
    rackId: int | None
    rackPosition: int | None
    rackName: str | None
    dataCenterId: int | None
    dataCenterName: str | None
    managementPort: bool
    portNaming: PortNaming
    portUnit: int
    portSlot: int
    id: int
    deviceType: DeviceType
    vendor: Vendor | None
    name: str
    model: str | None
    description: str | None
    version: int
    createdAt: str
    updatedAt: str
    portCount: int
    assignedPortCount: int
    cardCount: int


class PortResponse(PortNetworkConfig):
    effectiveFamily: Family
    effectiveSpeedGbps: int
    connectionId: int | None = None
    controller: Literal['A', 'B'] | None = None
    isManagement: bool = False
    id: int
    groupId: int
    family: Family
    number: int
    name: str
    slotNumber: int | None
    speedGbps: int
    label: str | None
    leadsTo: str | None


class GroupResponse(PortGroup):
    id: int


class DeviceDetail(DeviceSummary):
    expansionGroupId: int | None = None
    managementGroupId: int | None = None
    ports: list[PortResponse]
    portGroups: list[GroupResponse] | None = None
    networkCards: list[NetworkCard] | None = None


class DevicePage(BaseModel):
    items: list[DeviceSummary]
    total: int
    limit: int
    offset: int


class PreviewResponse(BaseModel):
    deviceId: int
    version: int
    removedCardCount: int
    removedPortCount: int
    removedAssignedPortCount: int
    removedConfiguredPortCount: int
    removedLabelledPortCount: int
    removedPorts: list[PortResponse]


class AuditEntry(BaseModel):
    id: int
    deviceId: int
    actorId: int | None
    action: str
    oldValue: dict | None
    newValue: dict | None
    createdAt: str


class AuditPage(BaseModel):
    items: list[AuditEntry]
    total: int
    limit: int
    offset: int
