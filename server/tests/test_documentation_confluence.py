"""Phase 3: fixed-origin reads, protected profiles and conflict-safe preview plans."""
import copy
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET
import httpx
import pytest
import auth
import auth_db
from documentation import repository as docs,confluence_profiles as profiles,confluence_client as connector,confluence_secrets as secrets
from documentation.confluence_render import render,sha
from tests.test_documentation_phase1 import make,publish,ROOT
from tests.test_dc_inventory import device

API=ROOT+'/confluence'
TOKEN='test-only-personal-access-token'
BASE='https://wiki.example.local/confluence'


@pytest.fixture(autouse=True)
def isolated_key_environment(monkeypatch):
    monkeypatch.delenv('DOCUMENTATION_SECRET_KEY',raising=False)


@pytest.fixture
def remote(monkeypatch):
    class Server:
        def __init__(self):
            self.calls=[];self.pages={};self.files={};self.failure=None;self.modern=True;self.on_get=None;self.version='9.2.1'
            self.pages['10']=self.page('10','Documentation home','<p>Home</p>')
        def page(self,id,title,storage,parent=None,version=1):
            return {'id':str(id),'title':title,'type':'page','status':'current','space':{'key':'TEST'},'version':{'number':version},
                    'body':{'storage':{'representation':'storage','value':storage}},'ancestors':[{'id':str(parent)}] if parent else [],
                    'operations':[{'operation':'read'},{'operation':'update'}]}
        def handle(self,request):
            self.calls.append(request)
            assert request.method=='GET'
            assert request.url.host=='wiki.example.local' and request.url.path.startswith('/confluence/rest/')
            assert request.headers['authorization']=='Bearer '+TOKEN
            if self.on_get:
                hook=self.on_get;self.on_get=None;hook()
            if self.failure:return self.failure(request)
            path=request.url.path.removeprefix('/confluence/')
            if path=='rest/api/server-information':return httpx.Response(200,json={'version':self.version}) if self.modern else httpx.Response(404,json={})
            if path=='rest/applinks/1.0/manifest.json':return httpx.Response(200,json={'typeId':'confluence','version':self.version})
            if path=='rest/api/user/current':return httpx.Response(200,json={'type':'known','username':'doc-bot','displayName':'Documentation service'})
            if path=='rest/api/space/TEST':return httpx.Response(200,json={'key':'TEST','name':'Test documentation','homepage':{'id':'10'}})
            match=re.fullmatch(r'rest/api/content/(\d+)/child/attachment',path)
            if match:return httpx.Response(200,json={'results':self.files.get(match[1],[]),'_links':{}})
            match=re.fullmatch(r'rest/api/content/(\d+)',path)
            if match:return httpx.Response(200,json=self.pages[match[1]]) if match[1] in self.pages else httpx.Response(404,json={})
            if path.endswith('/restriction/byOperation/read'):return httpx.Response(200,json={'restrictions':{'user':{'results':[]},'group':{'results':[]}}})
            if path=='rest/api/content':return httpx.Response(200,json={'results':[p for p in self.pages.values() if p['title']==request.url.params['title']]})
            raise AssertionError('Unexpected remote endpoint: '+path)
    state=Server()
    monkeypatch.setattr(connector,'HTTP_CLIENT',lambda **kwargs:httpx.Client(**kwargs,transport=httpx.MockTransport(state.handle)))
    return state


def create_profile(client,**extra):
    response=client.post(API+'/profiles',json={'name':'Local wiki','baseUrl':BASE,'spaceKey':'TEST','parentPageId':'10','token':TOKEN,**extra})
    assert response.status_code==201,response.text
    assert TOKEN not in response.text
    return response.json()


def url(item,number=1):return API+f"/documents/{item['id']}/versions/{number}/previews"


def preview(client,item,profile):
    response=client.post(url(item),json={'profileId':profile['id'],'expectedVersion':profile['version']})
    assert response.status_code==201,response.text
    assert TOKEN not in response.text
    return response.json()


def install_baseline(remote,plan):
    ids={page['key']:str(index+100) for index,page in enumerate(plan['pages'])}
    with docs.connection(True) as conn:
        for page in plan['pages']:
            identifier=ids[page['key']];parent=ids[page['parentKey']] if page['parentKey'] else '10'
            remote.pages[identifier]=remote.page(identifier,page['title'],page['storage'],parent)
            assets={}
            for i,asset in enumerate(page['attachments']):
                aid=str(10000+int(identifier)*100+i)
                remote.files.setdefault(identifier,[]).append({'id':aid,'title':asset['filename'],'version':{'number':1}})
                assets[asset['filename']]={'id':aid,'version':1,'sha256':asset['sha256']}
            conn.execute('''UPDATE documentation_confluence_pages SET remote_id=?,remote_version=1,last_published_revision=1,
                last_published_hash=?,last_remote_hash=?,last_attachments=? WHERE id=?''',
                (identifier,page['contentHash'],sha(page['storage']),json.dumps(assets),page['destinationId']))
    return ids


def test_profiles_encrypt_mask_keep_rotate_and_check_legacy_context_path(client,remote):
    profile=create_profile(client)
    key=secrets.key_path()
    assert key.stat().st_mode&0o777==0o600
    with docs.connection() as conn:
        row=profiles.row(conn,profile['id']);encrypted=row['credential']
        assert encrypted and TOKEN not in encrypted
        assert secrets.unseal(encrypted,profile['id'],BASE)==TOKEN
        assert TOKEN not in ''.join(r[0] for r in conn.execute('SELECT metadata FROM documentation_confluence_audit'))
    data={k:v for k,v in profile.items() if k in ('name','baseUrl','spaceKey','parentPageId','authMode','caPem','timeoutSeconds','enabled')}
    response=client.put(API+f"/profiles/{profile['id']}",json={**data,'name':'Renamed','expectedVersion':1,'token':None})
    assert response.status_code==200 and response.json()['version']==2
    with docs.connection() as conn:assert profiles.row(conn,profile['id'])['credential']==encrypted
    assert client.put(API+f"/profiles/{profile['id']}",json={**data,'expectedVersion':1}).status_code==409
    assert client.put(API+f"/profiles/{profile['id']}",json={**data,'baseUrl':'https://other.example.local','expectedVersion':2}).status_code==422
    remote.modern=False;remote.version='8.5.13'
    result=client.post(API+f"/profiles/{profile['id']}/check",json={'expectedVersion':2})
    assert result.status_code==200 and result.json()['ok'] is True
    assert result.json()['serverVersion']=='8.5.13' and result.json()['capabilities']['remoteWritesTested'] is False
    assert all(call.method=='GET' for call in remote.calls)
    assert any(call.url.path.endswith('manifest.json') for call in remote.calls)
    assert client.get(API+'/profiles').json()['items'][0]['lastCheck']['ok'] is True
    # Copying a credential to another profile/URL cannot authorize the request.
    with pytest.raises(docs.Invalid):secrets.unseal(encrypted,profile['id']+1,BASE)
    key.unlink()
    with pytest.raises(docs.Invalid):secrets.unseal(encrypted,profile['id'],BASE)


@pytest.mark.parametrize('status,code',[(302,'redirect'),(401,'authentication'),(403,'forbidden'),(404,'missing'),(429,'rate_limit'),(503,'server')])
def test_read_check_failures_are_sanitized_and_never_follow_redirects(client,remote,status,code):
    profile=create_profile(client)
    remote.failure=lambda request:httpx.Response(status,headers={'Location':'https://attacker.invalid/'+TOKEN},json={'message':TOKEN})
    response=client.post(API+f"/profiles/{profile['id']}/check",json={'expectedVersion':1})
    assert response.status_code==200 and response.json()['ok'] is False
    assert response.json()['code']==code and TOKEN not in response.text
    assert len(remote.calls)<=2
    with docs.connection() as conn:
        assert TOKEN not in profiles.row(conn,profile['id'])['last_check']
        assert TOKEN not in ''.join(r[0] for r in conn.execute('SELECT metadata FROM documentation_confluence_audit'))


@pytest.mark.parametrize('address',['http://wiki.example.local','https://user:password@wiki.example.local','https://127.0.0.1','https://169.254.169.254','https://wiki.example.local/../admin','https://wiki.example.local/%252e%252e','https://example.atlassian.net/wiki','https://bad host.example','https://wiki.example.local:0'])
def test_profile_validation_does_not_echo_credentials(client,address):
    response=client.post(API+'/profiles',json={'name':'Bad','baseUrl':address,'spaceKey':'TEST','token':TOKEN})
    assert response.status_code==422 and TOKEN not in response.text
    assert 'input' not in response.json()['detail'][0]
    response=client.post(API+'/profiles',json={'name':'Bad','baseUrl':BASE,'spaceKey':'TEST','token':TOKEN,'caPem':'PRIVATE KEY '+TOKEN})
    assert response.status_code==422 and TOKEN not in response.text
    assert client.get(API+'/profiles').json()['items']==[]


def test_preview_renders_native_hierarchy_code_and_detects_external_edits(client,remote):
    profile=create_profile(client)
    item=publish(client,make(client,notes='# Example\n\n- one\n- two\n\n```text\n<script>literal</script> ]]>\n```\n\n<script>alert(1)</script>'))
    first=preview(client,item,profile)
    assert first['readOnly'] and not first['remoteWritesPerformed'] and not first['hasConflicts']
    assert len(first['pages'])==12 and all(p['action']=='create' for p in first['pages'])
    root=first['pages'][0]
    assert '<ri:page ' in root['storage'] and root['parentKey'] is None
    assert all(p['parentKey']=='root' for p in first['pages'][1:])
    notes=next(p for p in first['pages'] if '<ac:structured-macro ac:name="code">' in p['storage'])
    assert '<ul>' in notes['storage'] and '<![CDATA[' in notes['storage'] and '&lt;script&gt;alert' in notes['storage']
    assert '<script>' not in notes['previewHtml']
    for page in first['pages']:ET.fromstring('<root xmlns:ac="urn:ac" xmlns:ri="urn:ri">'+page['storage']+'</root>')
    ids=install_baseline(remote,first)
    second=preview(client,item,profile)
    assert [p['destinationId'] for p in first['pages']]==[p['destinationId'] for p in second['pages']]
    assert all(p['action']=='unchanged' for p in second['pages'])
    remote.pages[ids['root']]['version']['number']=2
    remote.pages[ids['root']]['body']['storage']['value']='<p>Manual remote edit</p>'
    third=preview(client,item,profile)
    assert third['hasConflicts'] and all(p['action']=='conflict' for p in third['pages'])
    assert 'Manual remote edit' in third['pages'][0]['diff']
    assert any('externally' in issue for issue in third['pages'][0]['issues'])
    historical=client.get(url(item)+'/'+first['id']).json()
    assert historical['id']==first['id'] and not historical['hasConflicts']
    assert client.get(url(item)).json()['total']==3
    with docs.connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM documentation_confluence_pages').fetchone()[0]==12
        assert conn.execute('SELECT COUNT(*) FROM documentation_confluence_audit WHERE action=?',('prepare_preview',)).fetchone()[0]==3


def test_collision_missing_page_attachment_changes_and_source_access(client,remote):
    profile=create_profile(client);hardware=device(client,'Scoped switch')
    item=publish(client,make(client,templateId='switch',scopeSpec={'kind':'device','id':hardware['id']}))
    first=preview(client,item,profile)
    asset_page=next(p for p in first['pages'] if p['attachments'])
    assert asset_page['attachments'][0]['sha256'] and asset_page['attachments'][0]['action']=='create'
    remote.pages['42']=remote.page('42',first['pages'][0]['title'],'<p>Existing unowned page</p>')
    collision=preview(client,item,profile)
    assert collision['pages'][0]['action']=='conflict' and collision['pages'][0]['remoteId'] is None
    remote.pages.pop('42')
    ids=install_baseline(remote,first)
    unchanged=preview(client,item,profile)
    assert all(a['action']=='unchanged' for p in unchanged['pages'] for a in p['attachments'])
    remote.files[ids[asset_page['key']]][0]['version']['number']=2
    changed=preview(client,item,profile)
    assert next(p for p in changed['pages'] if p['key']==asset_page['key'])['attachments'][0]['action']=='conflict'
    remote.pages.pop(ids['root'])
    missing=preview(client,item,profile)
    assert any('missing' in issue for issue in missing['pages'][0]['issues'])
    auth_db.create_role('publish-without-source',['documentation.read','documentation.publish'])
    auth_db.create_user('confluence-publisher',auth.hash_password('Password123'),role='publish-without-source')
    client.post('/api/auth/login',json={'username':'confluence-publisher','password':'Password123'})
    before=len(remote.calls)
    assert client.get(API+'/profiles').status_code==200
    assert client.get(API+f"/profiles/{profile['id']}").status_code==403
    assert client.post(url(item),json={'profileId':profile['id'],'expectedVersion':1}).status_code==403
    assert client.get(url(item)+'/'+first['id']).status_code==403
    assert len(remote.calls)==before


def test_preview_requires_published_version_and_rolls_back_stale_profile(client,remote):
    profile=create_profile(client);item=make(client)
    client.post(ROOT+f"/{item['id']}/versions",json={'expectedVersion':1})
    assert client.post(url(item),json={'profileId':profile['id'],'expectedVersion':1}).status_code==422
    # Publish a new draft revision (saved baselines and publication stay distinct).
    saved=client.put(ROOT+f"/{item['id']}",json={**item['form'],'notes':'Ready','expectedVersion':1}).json()
    item=publish(client,saved)
    def change():
        with docs.connection(True) as conn:conn.execute('UPDATE documentation_confluence_profiles SET version=version+1 WHERE id=?',(profile['id'],))
    remote.on_get=change
    response=client.post(url(item,2),json={'profileId':profile['id'],'expectedVersion':1})
    assert response.status_code==409
    with docs.connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM documentation_confluence_previews').fetchone()[0]==0
        assert conn.execute('SELECT COUNT(*) FROM documentation_confluence_pages').fetchone()[0]==0


def test_profile_and_preview_tenant_boundaries_and_no_read_only_network_access(client,remote):
    profile=create_profile(client);item=publish(client,make(client));plan=preview(client,item,profile)
    auth_db.create_role('doc-reader',['documentation.read'])
    auth_db.create_user('confluence-reader',auth.hash_password('Password123'),role='doc-reader')
    client.post('/api/auth/login',json={'username':'confluence-reader','password':'Password123'})
    for response in [client.get(API+'/profiles'),client.post(API+f"/profiles/{profile['id']}/check",json={'expectedVersion':1}),client.get(url(item)+'/'+plan['id'])]:assert response.status_code==403
    client.post('/api/auth/logout')
    auth_db.create_user('confluence-admin',auth.hash_password('Password123'),role='admin')
    client.post('/api/auth/login',json={'username':'confluence-admin','password':'Password123'})
    tenant=client.post('/api/tenants',json={'name':'Confluence other tenant'}).json()['id']
    headers={'X-Tenant-ID':tenant}
    assert client.get(API+'/profiles',headers=headers).json()['items']==[]
    assert client.get(API+f"/profiles/{profile['id']}",headers=headers).status_code==404
    assert client.get(url(item)+'/'+plan['id'],headers=headers).status_code==404


def test_renderer_paginates_full_tables_uses_recorded_png_and_disables_external_images():
    document={'id':1,'form':{'title':'Example','notes':'![external](https://bad.invalid/image.png)'},
              'chapters':[{'id':'general','label':'General','sections':[{'title':'Notes','fields':[{'id':'notes','label':'Notes'}]}]}],
              'snapshot':{'tables':[{'id':'big','title':'Large table','chapter':'general','columns':['ID','Value'],'rows':[[i,'<pipe>|\nnext'] for i in range(237)]}]}}
    pages=render(document,1,'TEST')
    assert len(pages)==5
    assert sum(page['storage'].count('<td>') for page in pages)==237*2
    assert 'https://bad.invalid' not in ''.join(p['storage']+p['previewHtml'] for p in pages)
    assert all(page['parentKey']=='chapter-general' for page in pages if page['key'].startswith('table-'))


def test_preview_retains_permissions_for_old_baseline_after_scope_changes(client,remote):
    profile=create_profile(client);hardware=device(client,'Private baseline')
    item=publish(client,make(client,templateId='switch',scopeSpec={'kind':'device','id':hardware['id']}))
    first=preview(client,item,profile);install_baseline(remote,first)
    draft=client.post(ROOT+f"/{item['id']}/transition",json={'expectedVersion':item['version'],'action':'draft'}).json()
    saved=client.put(ROOT+f"/{item['id']}",json={**draft['form'],'scopeSpec':{'kind':'none'},'expectedVersion':draft['version']}).json()
    item=publish(client,saved)
    response=client.post(url(item,2),json={'profileId':profile['id'],'expectedVersion':1})
    assert response.status_code==201,response.text
    plan=response.json()
    assert 'device-visualization' in plan['requiredPermissions'] and plan['baselineVersions']==[1]
    auth_db.create_role('publish-manual-only',['documentation.read','documentation.publish'])
    auth_db.create_user('baseline-reader',auth.hash_password('Password123'),role='publish-manual-only')
    client.post('/api/auth/login',json={'username':'baseline-reader','password':'Password123'})
    assert client.get(ROOT+f"/{item['id']}/versions/2").status_code==200
    assert client.get(url(item,2)+'/'+plan['id']).status_code==403
    assert client.get(url(item,2)).json()['total']==0
    count=len(remote.calls)
    assert client.post(url(item,2),json={'profileId':profile['id'],'expectedVersion':1}).status_code==403
    assert len(remote.calls)==count


@pytest.mark.parametrize('failure,code',[
 ('timeout','timeout'),('html','format'),('too-large','limit'),('old-version','unsupported')])
def test_connection_timeout_size_login_page_and_unsupported_version(client,remote,monkeypatch,failure,code):
    profile=create_profile(client)
    def respond(request):
        if failure=='timeout':raise httpx.ReadTimeout('secret request failure '+TOKEN,request=request)
        if failure=='html':return httpx.Response(200,headers={'Content-Type':'text/html'},text='<html>'+TOKEN+'</html>')
        return httpx.Response(200,json={'message':'x'*1000})
    if failure=='old-version':remote.version='7.8.9'
    else:remote.failure=respond
    if failure=='too-large':monkeypatch.setattr(connector,'MAX_RESPONSE',100)
    result=client.post(API+f"/profiles/{profile['id']}/check",json={'expectedVersion':1})
    assert result.status_code==200 and result.json()['code']==code and not result.json()['ok']
    assert TOKEN not in result.text


def test_custom_ca_uses_strict_tls_and_ignores_proxies_and_redirects(client,remote,monkeypatch):
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from datetime import datetime,timedelta,timezone
    import ssl
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Test CA')]);now=datetime.now(timezone.utc)
    cert=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True).sign(key,hashes.SHA256())
    pem=cert.public_bytes(serialization.Encoding.PEM).decode()
    profile=create_profile(client,caPem=pem)
    captured=[]
    def transport(**kwargs):
        captured.append(kwargs)
        assert kwargs['verify'].check_hostname and kwargs['verify'].verify_mode==ssl.CERT_REQUIRED
        assert kwargs['trust_env'] is False and kwargs['follow_redirects'] is False
        return httpx.Client(**kwargs,transport=httpx.MockTransport(remote.handle))
    monkeypatch.setattr(connector,'HTTP_CLIENT',transport)
    response=client.post(API+f"/profiles/{profile['id']}/check",json={'expectedVersion':1})
    assert response.json()['ok'] and captured
    assert profile['hasCustomCA'] and 'caPem' not in client.get(API+'/profiles').json()['items'][0]


def test_profile_and_preview_audit_failures_roll_back_local_mutations(client,remote):
    import sqlite3
    with docs.connection(True) as conn:conn.execute("CREATE TRIGGER confluence_audit_failure BEFORE INSERT ON documentation_confluence_audit BEGIN SELECT RAISE(ABORT,'audit failure'); END")
    with pytest.raises(sqlite3.IntegrityError):create_profile(client)
    assert client.get(API+'/profiles').json()['items']==[]
    with docs.connection(True) as conn:conn.execute('DROP TRIGGER confluence_audit_failure')
    profile=create_profile(client);item=publish(client,make(client))
    with docs.connection(True) as conn:conn.execute("CREATE TRIGGER confluence_audit_failure BEFORE INSERT ON documentation_confluence_audit WHEN NEW.action='prepare_preview' BEGIN SELECT RAISE(ABORT,'audit failure'); END")
    with pytest.raises(sqlite3.IntegrityError):preview(client,item,profile)
    with docs.connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM documentation_confluence_previews').fetchone()[0]==0
        assert conn.execute('SELECT COUNT(*) FROM documentation_confluence_pages').fetchone()[0]==0


def test_remote_normalization_does_not_cause_repeated_updates(client,remote):
    profile=create_profile(client);item=publish(client,make(client));first=preview(client,item,profile)
    ids=install_baseline(remote,first)
    page=first['pages'][0];normalized=page['storage'].replace('><','>\n<')
    remote.pages[ids['root']]['body']['storage']['value']=normalized
    with docs.connection(True) as conn:conn.execute('UPDATE documentation_confluence_pages SET last_remote_hash=? WHERE id=?',(sha(normalized),page['destinationId']))
    result=preview(client,item,profile)
    assert result['pages'][0]['action']=='unchanged'
    assert any('normalized' in warning for warning in result['pages'][0]['advisories'])
