from pydantic import BaseModel, ConfigDict, Field, field_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class DataCenterWrite(StrictModel):
    name: str = Field(min_length=1,max_length=100)
    description: str | None = Field(default=None,max_length=500)

    @field_validator('name','description',mode='before')
    @classmethod
    def trim(cls,value,info):
        if isinstance(value,str):
            return value.strip() if info.field_name=='name' else value.strip() or None
        return value

class DataCenterUpdate(DataCenterWrite):
    expectedVersion: int = Field(strict=True,ge=1)

class RackCreate(DataCenterWrite):
    dataCenterId: int = Field(strict=True,ge=1)
    heightU: int = Field(strict=True,ge=1,le=100)

class RackUpdate(DataCenterUpdate):
    heightU: int = Field(strict=True,ge=1,le=100)

class ResourceDelete(StrictModel):
    expectedVersion: int = Field(strict=True,ge=1)
    confirmDelete: bool = Field(default=False,strict=True)

class Placement(StrictModel):
    expectedVersion: int = Field(strict=True,ge=1)
    rackId: int | None = Field(default=None,strict=True,ge=1)
    rackPosition: int | None = Field(default=None,strict=True,ge=1,le=100)
    heightU: int | None = Field(default=None,strict=True,ge=1,le=100)

class CablePanelCreate(DataCenterWrite):
    rackId: int = Field(strict=True,ge=1)
    rackPosition: int = Field(strict=True,ge=1,le=100)
