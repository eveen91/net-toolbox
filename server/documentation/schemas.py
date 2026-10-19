"""The opening DC documentation form; no inventory snapshots or imports."""
from typing import Literal
from datetime import date
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ScopeSpec(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind: Literal['none','dc','rack','device','subnet']='none'
    id: int|None=Field(default=None,strict=True,ge=1)
    dhcpVersionIds: list[str]=Field(default_factory=list,max_length=10)

    @model_validator(mode='after')
    def valid(self):
        if (self.kind=='none')!=(self.id is None):raise ValueError('Choose the DC, rack, device or network to include.')
        if len(set(self.dhcpVersionIds))!=len(self.dhcpVersionIds) or any(not value or len(value)>100 for value in self.dhcpVersionIds):raise ValueError('Choose unique published DHCP versions.')
        return self


class DCForm(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    templateId: Literal['network','switch','firewall','runbook']='network'
    scopeSpec: ScopeSpec=Field(default_factory=ScopeSpec)
    templateNotes: dict[str,str]=Field(default_factory=dict,max_length=20)
    title: str = Field(min_length=1, max_length=160)
    dcName: str = Field(default='', max_length=100)
    dcCode: str = Field(default='', max_length=100)
    environment: Literal['', 'production', 'disaster-recovery', 'test', 'development', 'mixed'] = ''
    operator: str = Field(default='', max_length=200)
    address: str = Field(default='', max_length=500)
    building: str = Field(default='', max_length=200)
    rooms: str = Field(default='', max_length=500)
    timezone: str = Field(default='', max_length=100)
    purpose: str = Field(default='', max_length=5000)
    scope: str = Field(default='', max_length=5000)
    exclusions: str = Field(default='', max_length=3000)
    criticality: Literal['', 'critical', 'high', 'standard', 'low'] = ''
    ownerTeam: str = Field(default='', max_length=200)
    technicalOwner: str = Field(default='', max_length=500)
    serviceOwner: str = Field(default='', max_length=500)
    operationsContact: str = Field(default='', max_length=1000)
    emergencyContact: str = Field(default='', max_length=1000)
    providerContact: str = Field(default='', max_length=1000)
    accessProcedure: str = Field(default='', max_length=5000)
    accessHours: str = Field(default='', max_length=500)
    deliveryProcedure: str = Field(default='', max_length=3000)
    power: str = Field(default='', max_length=5000)
    cooling: str = Field(default='', max_length=3000)
    fireProtection: str = Field(default='', max_length=3000)
    physicalSecurity: str = Field(default='', max_length=3000)
    connectivity: str = Field(default='', max_length=5000)
    maintenanceWindow: str = Field(default='', max_length=1000)
    monitoring: str = Field(default='', max_length=3000)
    backupRecovery: str = Field(default='', max_length=5000)
    dependencies: str = Field(default='', max_length=3000)
    references: str = Field(default='', max_length=5000)
    notes: str = Field(default='', max_length=5000)
    author: str = Field(default='', max_length=200)
    reviewDate: str = Field(default='', max_length=10)

    floorPlans: str = Field(default='', max_length=5000)
    roomLayout: str = Field(default='', max_length=5000)
    rackLayout: str = Field(default='', max_length=5000)
    physicalConstraints: str = Field(default='', max_length=5000)
    equipmentScope: str = Field(default='', max_length=5000)
    equipmentIdentification: str = Field(default='', max_length=5000)
    equipmentManagement: str = Field(default='', max_length=5000)
    equipmentGaps: str = Field(default='', max_length=5000)
    cablingStandards: str = Field(default='', max_length=5000)
    cableIdentification: str = Field(default='', max_length=5000)
    patchPanels: str = Field(default='', max_length=5000)
    interRackLinks: str = Field(default='', max_length=5000)
    addressingDesign: str = Field(default='', max_length=5000)
    routingDesign: str = Field(default='', max_length=5000)
    securityZones: str = Field(default='', max_length=5000)
    interDcDesign: str = Field(default='', max_length=5000)
    carrierCircuits: str = Field(default='', max_length=5000)
    carrierHandoffs: str = Field(default='', max_length=5000)
    externalRedundancy: str = Field(default='', max_length=5000)
    powerDistribution: str = Field(default='', max_length=5000)
    devicePowerMapping: str = Field(default='', max_length=5000)
    powerCapacity: str = Field(default='', max_length=5000)
    nameAddressServices: str = Field(default='', max_length=5000)
    authenticationServices: str = Field(default='', max_length=5000)
    loggingServices: str = Field(default='', max_length=5000)
    configurationBackups: str = Field(default='', max_length=5000)
    haDesign: str = Field(default='', max_length=5000)
    recoveryPriorities: str = Field(default='', max_length=5000)
    resilienceTests: str = Field(default='', max_length=5000)
    supportLifecycle: str = Field(default='', max_length=5000)
    maintenanceSchedule: str = Field(default='', max_length=5000)
    changeHistory: str = Field(default='', max_length=5000)

    @model_validator(mode='after')
    def template_valid(self):
        from .templates import TEMPLATES
        if self.templateId!='runbook' and not self.dcName:raise ValueError('A documented DC, network or device name is required')
        if self.scopeSpec.kind not in TEMPLATES[self.templateId]['scopes']:raise ValueError('Document type does not support that scope')
        permitted={f['id'] for page in TEMPLATES[self.templateId]['pages'] for section in page['sections'] for f in section['fields'] if f.get('note')}
        if any(key not in permitted or len(value)>5000 for key,value in self.templateNotes.items()):raise ValueError('Unknown or oversized template section')
        return self

    @field_validator('reviewDate')
    @classmethod
    def validate_date(cls, value):
        if value: date.fromisoformat(value)
        return value


class SaveDC(DCForm):
    expectedVersion: int = Field(strict=True, ge=1)


class CreateVersion(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    expectedVersion: int = Field(strict=True, ge=1)
    description: str = Field(default='', max_length=1000)


class Expected(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expectedVersion:int=Field(strict=True,ge=1)

class Transition(Expected):
    action:Literal['submit','draft','publish']
    description:str=Field(default='',max_length=1000)

class Refresh(Expected):
    snapshotDigest:str=Field(min_length=64,max_length=64)

class Coverage(BaseModel):
    model_config=ConfigDict(extra='forbid')
    templateId:Literal['network','switch','firewall','runbook']='network'
    scopeSpec:ScopeSpec
