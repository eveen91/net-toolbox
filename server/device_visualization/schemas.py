from typing import Literal
from .naming import PortNaming
from .vlans import normalize_trunk
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Family = Literal['ethernet', 'sfp', 'qsfp']
DeviceType = Literal['switch', 'firewall', 'server']
Vendor = Literal['checkpoint', 'fortigate', 'generic']
SPEEDS = {'ethernet': (1, 10), 'sfp': (10, 25), 'qsfp': (40, 100)}
COUNTS = {'ethernet': 96, 'sfp': 48, 'qsfp': 16}


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
    id: int | None = Field(default=None, strict=True, ge=1)
    slotNumber: int = Field(strict=True, ge=1, le=16)
    name: str | None = Field(default=None, max_length=60)
    count: int = Field(strict=True, ge=1, le=8)

    @field_validator('name', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() or None if isinstance(value, str) else value


class DeviceConfig(StrictModel):
    deviceType: DeviceType
    vendor: Vendor | None = None
    name: str = Field(min_length=1, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)
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
        if self.deviceType != 'switch' and (self.portNaming != 'family' or self.portUnit != 1 or self.portSlot != 1):
            raise ValueError('Custom port naming is only supported for switches')
        if self.deviceType == 'firewall':
            if self.vendor is None:
                raise ValueError('Choose a firewall vendor')
        elif self.vendor is not None:
            raise ValueError('Vendor is only supported for firewalls')
        if self.deviceType == 'server':
            if not self.networkCards or 'portGroups' in self.model_fields_set:
                raise ValueError('Servers require networkCards and do not accept portGroups')
            if len({card.slotNumber for card in self.networkCards}) != len(self.networkCards):
                raise ValueError('Network card slots must be unique')
            ids = [card.id for card in self.networkCards if card.id is not None]
            if len(set(ids)) != len(ids):
                raise ValueError('Network card IDs must be unique')
            groups = self.networkCards
        else:
            if self.portGroups is None or 'networkCards' in self.model_fields_set:
                raise ValueError('Switches/firewalls require portGroups and do not accept networkCards')
            if len(self.portGroups) != 3 or {g.family for g in self.portGroups} != set(SPEEDS):
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


class PortVlanConfig(BaseModel):
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


class PortAssignment(PortVlanConfig, StrictModel):
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


class PortResponse(PortVlanConfig):
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
