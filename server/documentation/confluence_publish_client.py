"""Explicit writes on the existing verified connection; ambiguous writes never retry here."""
import json
import re
import time
from urllib.parse import quote
import httpx
from .confluence_client import Client,RemoteError,MAX_RESPONSE


class WriteError(RemoteError):
    def __init__(self,code,message,status=None,uncertain=False,retry_after=0):
        super().__init__(code,message,status)
        self.uncertain=uncertain;self.retry_after=retry_after


def numeric(value):
    value=str(value)
    if not re.fullmatch(r'[1-9][0-9]{0,29}',value):raise RemoteError('identity','Invalid remote identity.')
    return value


class PublishingClient(Client):
    def write(self,method,path,**kwargs):
        if method not in ('POST','PUT') or not re.fullmatch(r'rest/api/content(?:/[1-9][0-9]*)?(?:/child/attachment)?',path):raise RemoteError('path','Invalid publication endpoint.')
        remaining=self.deadline-time.monotonic()
        if remaining<=0:raise WriteError('timeout','Publication time budget exhausted before the request.')
        try:
            with self.http.stream(method,path,timeout=min(self.profile['timeoutSeconds'],remaining),**kwargs) as response:
                status=response.status_code
                if status>=300:
                    uncertain=status>=500 or 300<=status<400
                    code={400:'rejected',401:'authentication',403:'forbidden',404:'missing',409:'conflict',429:'rate_limit'}.get(status,'redirect' if status<400 else 'server')
                    delay=response.headers.get('Retry-After','0')
                    delay=min(3600,int(delay)) if delay.isdigit() else 30 if status==429 else 0
                    raise WriteError(code,'Confluence rejected the write; review access or conflicts.' if not uncertain else 'Confluence returned a server error; the write result must be reconciled.',status,uncertain,delay)
                chunks=[];size=0
                for chunk in response.iter_bytes():
                    size+=len(chunk)
                    if size>MAX_RESPONSE or time.monotonic()>self.deadline:raise WriteError('response','The write response could not be read completely; reconcile its result.',uncertain=True)
                    chunks.append(chunk)
                if response.headers.get('content-type','').split(';')[0]!='application/json':raise ValueError()
                value=json.loads(b''.join(chunks))
                if not isinstance(value,dict):raise ValueError()
                return value
        except (httpx.ConnectError,httpx.ConnectTimeout):raise WriteError('connect','The connection failed before a write could be sent. Retry after checking connectivity.') from None
        except httpx.TransportError:raise WriteError('transport','The write response was interrupted; reconcile before sending another write.',uncertain=True) from None
        except (ValueError,UnicodeError):raise WriteError('format','The write returned an unreadable response; reconcile its result.',uncertain=True) from None

    def put_page(self,identifier,payload):return self.write('PUT','rest/api/content/'+numeric(identifier),json=payload)
    def create_page(self,payload):return self.write('POST','rest/api/content',json=payload)

    def upload(self,page_id,filename,content,operation):
        # Content-addressed files are create-only. A racing filename must reject,
        # never create a new version of someone else's attachment.
        return self.write('POST',f'rest/api/content/{numeric(page_id)}/child/attachment',params={'allowDuplicated':'false'},
            headers={'X-Atlassian-Token':'nocheck'},data={'comment':'net-toolbox:'+operation,'minorEdit':'true'},files={'file':(filename,content,'image/png')})

    def binary(self,page_id,filename,version):
        if not re.fullmatch(r'[a-zA-Z0-9_-]+\.png',filename):raise RemoteError('path','Invalid frozen attachment filename.')
        path=f'download/attachments/{numeric(page_id)}/{quote(filename,safe="")}'
        try:
            with self.http.stream('GET',path,params={'version':int(version)},timeout=self.profile['timeoutSeconds']) as response:
                if response.status_code!=200:raise RemoteError('attachment_read','Cannot verify attachment bytes at the configured origin.',response.status_code)
                chunks=[];size=0
                for chunk in response.iter_bytes():
                    size+=len(chunk)
                    if size>64*1024*1024 or time.monotonic()>self.deadline:raise RemoteError('limit','Attachment verification exceeded the bounded read budget.')
                    chunks.append(chunk)
                return b''.join(chunks)
        except httpx.TransportError:raise RemoteError('transport','Attachment verification failed; no repeat upload was sent.') from None

