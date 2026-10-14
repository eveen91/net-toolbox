import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .vendor.generator import validate_configuration


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Options(StrictModel):
    default_lease_time: int | None = Field(default=None, ge=1, le=2147483647)
    max_lease_time: int | None = Field(default=None, ge=1, le=2147483647)
    domain: str | None = Field(default=None, max_length=253)
    dns: list[str] | None = Field(default=None, min_length=1, max_length=3)


class Pool(StrictModel):
    start: str = Field(max_length=15)
    end: str = Field(max_length=15)
    active: bool = True


class Reservation(StrictModel):
    id: str = Field(min_length=1, max_length=63)
    mac: str = Field(max_length=17)
    ip: str = Field(max_length=15)
    active: bool = True


class Subnet(Options):
    cidr: str = Field(max_length=18)
    gateway: str | None = Field(default=None, max_length=15)
    interface_address: str | list[str] | None = None
    gaia_host_name_fallback: bool = False
    active: bool = True
    pools: list[Pool] = Field(default_factory=list, max_length=1)
    reservations: list[Reservation] = Field(default_factory=list, max_length=10000)


class Configuration(Options):
    firewall: str = Field(min_length=1, max_length=63)
    profile: Literal['R81.10', 'R82.10']
    subnets: list[Subnet] = Field(default_factory=list, max_length=512)

    @model_validator(mode='after')
    def validate_draft(self):
        data = self.model_dump(exclude_none=True)
        if len(json.dumps(data).encode()) > 1024 * 1024:
            raise ValueError('Configuration exceeds 1 MiB')
        if sum(len(subnet.reservations) for subnet in self.subnets) > 10000:
            raise ValueError('Use at most 10,000 reservations per configuration')
        validate_configuration(data, complete=False)
        return self


class Create(StrictModel):
    configuration: Configuration


class Save(Create):
    expectedRevision: int = Field(ge=1)


class Revision(StrictModel):
    expectedRevision: int = Field(ge=1)


class Publish(Revision):
    description: str = Field(min_length=1, max_length=2000)

    @model_validator(mode='after')
    def note(self):
        self.description = self.description.strip()
        if not self.description:
            raise ValueError('Describe the version before publishing')
        return self


class Restore(Revision):
    versionId: str = Field(min_length=36, max_length=36)
