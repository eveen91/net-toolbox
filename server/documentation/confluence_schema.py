"""Bounded Confluence Server/Data Center connection and preview inputs."""
import ipaddress
import re
import ssl
from urllib.parse import urlsplit,urlunsplit,unquote
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,SecretStr,field_validator


class ConnectionProfile(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    name:str=Field(min_length=1,max_length=100)
    baseUrl:str=Field(min_length=1,max_length=500)
    spaceKey:str=Field(min_length=1,max_length=255,pattern=r'^[A-Za-z0-9_-]+$')
    parentPageId:str|None=Field(default=None,pattern=r'^[1-9][0-9]{0,29}$')
    authMode:Literal['pat']='pat'
    token:SecretStr|None=Field(default=None,max_length=8192)
    caPem:str=Field(default='',max_length=65536)
    timeoutSeconds:int=Field(default=10,strict=True,ge=3,le=30)
    enabled:bool=True

    @field_validator('baseUrl')
    @classmethod
    def url(cls,value):
        try:
            url=urlsplit(value);host=url.hostname;port=url.port
            if (port is not None and port<1) or url.scheme!='https' or not host or url.username or url.password or url.query or url.fragment:raise ValueError()
            if host.endswith('.atlassian.net'):raise ValueError()
            try:
                address=ipaddress.ip_address(host)
                if address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified:raise ValueError('Unusable Confluence address')
            except ValueError as exc:
                if str(exc)=='Unusable Confluence address':raise
                host=host.encode('idna').decode('ascii')
                if len(host)>253 or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*',host):raise ValueError()
            if host.lower() in ('localhost','localhost.localdomain','metadata.google.internal'):raise ValueError()
            decoded=unquote(url.path)
            if '%' in decoded or '\\' in decoded or any(p in ('.','..') for p in decoded.split('/')) or any(ord(c)<33 for c in decoded):raise ValueError()
            if not re.fullmatch(r'[A-Za-z0-9._~/-]*',url.path):raise ValueError()
            origin=('['+host+']' if ':' in host else host.lower())+(f':{port}' if port and port!=443 else '')
            return urlunsplit(('https',origin,url.path.rstrip('/'),'',''))
        except ValueError:raise ValueError('Use an on-premises HTTPS base URL, including its context path, without credentials, query or fragment.')

    @field_validator('caPem')
    @classmethod
    def ca(cls,value):
        if value:
            if 'PRIVATE KEY' in value:raise ValueError('Supply a public CA certificate, not a private key.')
            try:ssl.create_default_context(cadata=value)
            except ssl.SSLError:raise ValueError('The custom CA must be a valid PEM certificate bundle.')
        return value


class UpdateConnection(ConnectionProfile):
    expectedVersion:int=Field(strict=True,ge=1)


class ConnectionExpected(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expectedVersion:int=Field(strict=True,ge=1)


class ConfluencePreviewRequest(ConnectionExpected):
    profileId:int=Field(strict=True,ge=1)


class PublishRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    previewId:str=Field(pattern=r'^[a-f0-9-]{36}$')
    expectedVersion:int=Field(strict=True,ge=1)
    audienceConfirmed:Literal[True]
    keepRemoteKeys:list[str]=Field(default_factory=list,max_length=200)
    replaceReviewedKeys:list[str]=Field(default_factory=list,max_length=200)


class JobExpected(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expectedRevision:int=Field(strict=True,ge=1)


class JobControl(JobExpected):
    action:Literal['pause','abandon']


class JobRevalidate(JobExpected):
    expectedProfileVersion:int=Field(strict=True,ge=1)
    audienceConfirmed:Literal[True]


class JobResolve(JobExpected):
    remotePageId:str|None=Field(default=None,pattern=r'^[1-9][0-9]{0,29}$')
    notAppliedConfirmed:bool=False
