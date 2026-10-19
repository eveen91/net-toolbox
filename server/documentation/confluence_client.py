"""HTTPS-only, fixed-origin, GET-only Confluence Server/DC REST adapter."""
import json
import re
import ssl
import time
from contextlib import AbstractContextManager
from urllib.parse import quote
import httpx
from .confluence_secrets import unseal

HTTP_CLIENT=httpx.Client
MAX_RESPONSE=8*1024*1024
MAX_REQUESTS=250


class RemoteError(Exception):
    def __init__(self,code,message,status=None):
        self.code=code;self.message=message;self.status=status
        super().__init__(message)


class Client(AbstractContextManager):
    def __init__(self,profile,credential):
        self.profile=profile;self.deadline=time.monotonic()+90;self.requests=0
        token=unseal(credential,profile['id'],profile['baseUrl'])
        context=ssl.create_default_context(cadata=profile['caPem'] or None)
        self.http=HTTP_CLIENT(base_url=profile['baseUrl']+'/',headers={'Authorization':'Bearer '+token,'Accept':'application/json'},
            verify=context,timeout=profile['timeoutSeconds'],follow_redirects=False,trust_env=False)

    def __exit__(self,*args):self.http.close()

    def get(self,path,params=None,optional=False):
        # All callers supply fixed endpoint fragments/validated numeric IDs.
        if (not path.startswith('rest/api/') and path!='rest/applinks/1.0/manifest.json') or '?' in path or '..' in path or '\\' in path:raise RemoteError('path','Invalid Confluence REST path.')
        remaining=self.deadline-time.monotonic()
        self.requests+=1
        if remaining<=0 or self.requests>MAX_REQUESTS:raise RemoteError('limit','Confluence preview exceeded its 90-second / 250-request budget. Use a smaller document.')
        try:
            with self.http.stream('GET',path,params=params,timeout=min(self.profile['timeoutSeconds'],remaining)) as response:
                status=response.status_code
                if status==404 and optional:return None
                if 300<=status<400:raise RemoteError('redirect','Confluence redirected the request. Check the exact HTTPS base URL/context path; redirects are not followed.',status)
                errors={401:('authentication','Confluence rejected the personal access token.'),403:('forbidden','The service identity lacks access to this Confluence resource.'),
                        404:('missing','The Confluence resource was not found or is not visible to the service identity.'),429:('rate_limit','Confluence rate limit reached. Retry later.')}
                if status in errors:raise RemoteError(*errors[status],status)
                if status>=400:raise RemoteError('server','Confluence REST request failed. No remote changes were made.',status)
                if response.headers.get('content-type','').split(';')[0].strip().lower()!='application/json':raise RemoteError('format','Expected Confluence REST JSON; the server may have returned a login or proxy page.')
                chunks=[];size=0
                for chunk in response.iter_bytes():
                    size+=len(chunk)
                    if size>MAX_RESPONSE:raise RemoteError('limit','Confluence returned more than 8 MiB for one REST response.')
                    if time.monotonic()>self.deadline:raise RemoteError('timeout','Confluence read exceeded its 90-second deadline.')
                    chunks.append(chunk)
                value=json.loads(b''.join(chunks))
                if not isinstance(value,dict):raise ValueError()
                return value
        except httpx.TimeoutException:raise RemoteError('timeout','Confluence timed out. No remote changes were made.') from None
        except httpx.TransportError:raise RemoteError('transport','Cannot reach or verify Confluence. Check the address, network and trusted CA certificate.') from None
        except (ValueError,UnicodeError):raise RemoteError('format','Confluence returned invalid REST JSON.') from None

    def page(self,identifier,optional=False):
        if not re.fullmatch(r'[1-9][0-9]{0,29}',str(identifier)):raise RemoteError('identity','Invalid saved Confluence page ID.')
        result=self.get(f'rest/api/content/{identifier}',{'expand':'body.storage,version,ancestors,space,operations'},optional)
        if result and str(result.get('id'))!=str(identifier):raise RemoteError('identity','Confluence returned a different page identity.')
        return result

    def attachments(self,identifier):
        if not re.fullmatch(r'[1-9][0-9]{0,29}',str(identifier)):raise RemoteError('identity','Invalid Confluence attachment parent ID.')
        result=[];start=0
        while True:
            data=self.get(f'rest/api/content/{identifier}/child/attachment',{'limit':100,'start':start,'expand':'version,metadata'})
            batch=data.get('results')
            if not isinstance(batch,list) or any(not isinstance(item,dict) for item in batch):raise RemoteError('format','Confluence returned an invalid attachment collection.')
            result.extend(batch)
            if len(result)>1000:raise RemoteError('limit','More than 1,000 remote attachments on one page; inspect a smaller destination.')
            # Never follow arbitrary URLs from _links.next, even on the same host.
            if not data.get('_links',{}).get('next'):break
            if not batch:raise RemoteError('format','Confluence attachment pagination did not advance.')
            start+=len(batch)
        return result

    def title_matches(self,title):
        data=self.get('rest/api/content',{'spaceKey':self.profile['spaceKey'],'title':title,'type':'page','status':'current','limit':2})
        results=data.get('results')
        if not isinstance(results,list) or any(not isinstance(item,dict) for item in results):raise RemoteError('format','Confluence returned an invalid title search.')
        if any(not re.fullmatch(r'[1-9][0-9]{0,29}',str(item.get('id',''))) for item in results):raise RemoteError('format','Confluence title search omitted page identities.')
        return results

    def probe(self):
        information=self.get('rest/api/server-information',optional=True)
        if information is None:
            information=self.get('rest/applinks/1.0/manifest.json')
            if information.get('typeId')!='confluence':raise RemoteError('product','The configured application did not identify itself as Confluence.')
        version=information.get('versionNumber') or information.get('version') or ''
        if not isinstance(version,str) or not re.fullmatch(r'\d+\.\d+(?:\.\d+)?(?:[-.A-Za-z0-9]*)',version):raise RemoteError('version','The installed Confluence version could not be verified.')
        major,minor=map(int,version.split('.')[:2])
        if (major,minor)<(7,9):raise RemoteError('unsupported','This connector requires Confluence Server/Data Center 7.9+ with personal access tokens; no password fallback is used.')
        identity=self.get('rest/api/user/current')
        if identity.get('type') in ('anonymous','unknown') or not(identity.get('username') or identity.get('userKey') or identity.get('accountId')):raise RemoteError('authentication','Confluence did not confirm an authenticated service identity.')
        space=self.get('rest/api/space/'+quote(self.profile['spaceKey'],safe=''),{'expand':'homepage,permissions'})
        if space.get('key')!=self.profile['spaceKey']:raise RemoteError('space','Confluence returned a different space.')
        parent=self.page(self.profile['parentPageId']) if self.profile['parentPageId'] else None
        if parent and (parent.get('space',{}).get('key')!=self.profile['spaceKey'] or parent.get('type')!='page' or parent.get('status')!='current'):raise RemoteError('parent','The parent must be a current page in the configured space.')
        sample=parent
        if not sample:
            homepage=space.get('homepage',{}).get('id')
            if homepage:sample=self.page(homepage)
        storage=bool(sample and isinstance(sample.get('body',{}).get('storage',{}).get('value'),str))
        if not storage:raise RemoteError('storage','Storage representation could not be read. Configure a readable parent page or space homepage.')
        # Verify the actual read API, never infer upload/write privileges from it.
        self.attachments(sample['id'])
        return {'serverVersion':version,'identity':str(identity.get('displayName') or identity.get('username') or 'Authenticated service')[:200],
                'spaceKey':space['key'],'spaceName':str(space.get('name',''))[:255],
                'parentPageId':str(parent['id']) if parent else None,'parentTitle':str(parent['title'])[:255] if parent else None,
                'capabilities':{'authenticatedRead':True,'storageRead':True,'attachmentRead':True,'remoteWritesTested':False},
                'advisories':['Read access does not prove page creation, attachment upload or the intended reader audience. Verify these before Phase 4 publication.'],
                'sampleOperations':sorted({str(item['operation']) for item in sample.get('operations',[]) if isinstance(item,dict) and item.get('operation') in ('read','update','create','delete','administer')})}
