import re
from typing import Annotated, Literal
from pydantic import BaseModel, Field, field_validator, model_validator

MAX_SOURCES = 16
MAX_DESTINATIONS = 64
MAX_PORTS = 32
MAX_COMBINATIONS = 1024
HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,252}$")
Port = Annotated[int, Field(strict=True, ge=1, le=65535)]


def hostname(value):
    value = value.strip()
    if not HOST_RE.fullmatch(value):
        raise ValueError("Enter a hostname or IPv4 address without spaces or shell characters")
    return value


class Source(BaseModel):
    host: str
    os: Literal["linux", "windows"]
    _host = field_validator("host")(hostname)


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=4096, repr=False)


class RunRequest(BaseModel):
    sources: list[Source] = Field(min_length=1, max_length=MAX_SOURCES)
    destinations: list[str] = Field(min_length=1, max_length=MAX_DESTINATIONS)
    ports: list[Port] = Field(min_length=1, max_length=MAX_PORTS)
    linux_credentials: Credentials | None = None
    windows_credentials: Credentials | None = None
    connect_timeout_seconds: int = Field(default=5, strict=True, ge=1, le=60)
    ssh_port: Port = 22
    winrm_port: Port = 5985
    winrm_transport: Literal["ntlm", "kerberos", "basic", "credssp"] = "ntlm"
    winrm_scheme: Literal["http", "https"] = "http"

    @field_validator("destinations")
    @classmethod
    def validate_destinations(cls, values):
        return [hostname(value) for value in values]

    @model_validator(mode="after")
    def validate_run(self):
        combinations = len(self.sources) * len(self.destinations) * len(self.ports)
        if combinations > MAX_COMBINATIONS:
            raise ValueError(f"At most {MAX_COMBINATIONS} source × destination × port combinations are allowed")
        if self.winrm_transport == "basic" and self.winrm_scheme != "https":
            raise ValueError("Basic WinRM authentication requires HTTPS")
        return self
