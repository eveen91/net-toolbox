"""Phase 4 regression tests: durable writes, fencing and ambiguous-result recovery."""
import json
import re
import sqlite3
import time
from email import policy
from email.parser import BytesParser
import httpx
import pytest
import auth
import auth_db
from documentation import repository as docs,confluence_client as connector
from tests.test_documentation_confluence import remote,create_profile,preview,TOKEN,API,isolated_key_environment
from tests.test_documentation_phase1 import make,publish,ROOT
from tests.test_dc_inventory import device


@pytest.fixture
def writable(remote,monkeypatch):
    original=remote.handle
    remote.writes=[];remote.binaries={};remote.fail=None;remote.before_write=None;remote.acl_changed=False;remote.next_id=100
    def handle(request):
        path=request.url.path.removeprefix('/confluence/')
        if request.method=='GET' and path.endswith('/restriction/byOperation/read') and remote.acl_changed:
            remote.calls.append(request)
            return httpx.Response(200,json={'restrictions':{'user':{'results':[]},'group':{'results':[{'name':'Changed audience'}]}}})
        if request.method=='GET' and path.startswith('download/attachments/'):
            remote.calls.append(request)
            _,_,parent,filename=path.split('/',3)
            data=remote.binaries.get((parent,filename))
            return httpx.Response(200,content=data,headers={'content-type':'image/png'}) if data else httpx.Response(404,json={})
        if request.method=='GET':return original(request)
        remote.calls.append(request);remote.writes.append(request)
        assert request.headers['authorization']=='Bearer '+TOKEN
        if remote.before_write:
            action=remote.before_write;remote.before_write=None;action()
        if remote.fail=='connect':remote.fail=None;raise httpx.ConnectError('Connection failed '+TOKEN,request=request)
        if remote.fail=='forbidden':remote.fail=None;return httpx.Response(403,json={'message':TOKEN})
        if remote.fail=='rate_limit':remote.fail=None;return httpx.Response(429,headers={'Retry-After':'1'},json={'message':TOKEN})
        if path=='rest/api/content' and request.method=='POST':
            data=json.loads(request.content)
            if any(p['title']==data['title'] for p in remote.pages.values()):return httpx.Response(409,json={})
            identifier=str(remote.next_id);remote.next_id+=1
            parent=data.get('ancestors',[])
            remote.pages[identifier]=remote.page(identifier,data['title'],data['body']['storage']['value'],parent[-1]['id'] if parent else None)
            if remote.fail=='after_create':remote.fail=None;raise httpx.ReadTimeout('Reply lost '+TOKEN,request=request)
            return httpx.Response(200,json={'id':identifier})
        match=re.fullmatch(r'rest/api/content/(\d+)',path)
        if match and request.method=='PUT':
            data=json.loads(request.content);current=remote.pages[match[1]]
            if data['version']['number']!=current['version']['number']+1:return httpx.Response(409,json={})
            current.update(title=data['title'],body=data['body'],version=data['version'])
            if remote.fail=='after_update':remote.fail=None;raise httpx.ReadTimeout('Reply lost',request=request)
            return httpx.Response(200,json={'id':match[1]})
        match=re.fullmatch(r'rest/api/content/(\d+)/child/attachment',path)
        if match and request.method=='POST':
            assert request.url.params['allowDuplicated']=='false'
            assert request.headers['x-atlassian-token']=='nocheck'
            message=BytesParser(policy=policy.default).parsebytes(('Content-Type: '+request.headers['content-type']+'\r\n\r\n').encode()+request.content)
            parts={part.get_param('name',header='content-disposition'):part for part in message.iter_parts()}
            filename=parts['file'].get_filename();comment=parts['comment'].get_content().strip();parent=match[1]
            if any(f['title']==filename for f in remote.files.get(parent,[])):return httpx.Response(409,json={})
            identifier=str(10000+remote.next_id);remote.next_id+=1
            record={'id':identifier,'title':filename,'version':{'number':1},'metadata':{'comment':comment}}
            remote.files.setdefault(parent,[]).append(record);remote.binaries[(parent,filename)]=parts['file'].get_payload(decode=True)
            if remote.fail=='after_upload':remote.fail=None;raise httpx.ReadTimeout('Upload reply lost',request=request)
            return httpx.Response(200,json={'results':[record]})
        raise AssertionError('Unexpected mutation '+request.method+' '+path)
    monkeypatch.setattr(connector,'HTTP_CLIENT',lambda **kwargs:httpx.Client(**kwargs,transport=httpx.MockTransport(handle)))
    return remote


def jobs_url(item,number=1):return API+f"/documents/{item['id']}/versions/{number}/jobs"


def start(client,item,plan,number=1,**extra):
    response=client.post(jobs_url(item,number),json={'previewId':plan['id'],'expectedVersion':plan['profileVersion'],'audienceConfirmed':True,**extra})
    assert response.status_code==201,response.text
    return response.json()


def advance(client,item,job,number=1):
    response=client.post(jobs_url(item,number)+'/'+job['id']+'/advance',json={'expectedRevision':job['revision']})
    assert response.status_code==200,response.text
    assert TOKEN not in response.text
    return response.json()


def complete(client,item,job,number=1):
    for _ in range(100):
        if job['status']=='succeeded':return job
        assert job['status'] in ('pending','paused','running'),job
        job=advance(client,item,job,number)
    raise AssertionError('Publication did not finish')


def setup(client,hardware=False):
    profile=create_profile(client)
    scope={'kind':'device','id':device(client,'Published switch')['id']} if hardware else {'kind':'none'}
    item=publish(client,make(client,templateId='switch',scopeSpec=scope))
    return profile,item


def test_create_attachments_republish_without_duplicates_or_writes(client,writable):
    profile,item=setup(client,True);plan=preview(client,item,profile)
    job=start(client,item,plan)
    assert not writable.writes and job['completed']==0
    duplicate=start(client,item,plan);assert duplicate['id']==job['id']
    done=complete(client,item,job)
    assert done['completed']==done['total'] and done['status']=='succeeded'
    assert len(writable.pages)==len(plan['pages'])+1
    assert sum(len(a) for a in writable.files.values())==sum(len(p['attachments']) for p in plan['pages'])
    for page in plan['pages']:
        with docs.connection() as conn:mapping=conn.execute('SELECT * FROM documentation_confluence_pages WHERE id=?',(page['destinationId'],)).fetchone()
        assert mapping['last_published_revision']==1 and mapping['remote_version']==1
    count=len(writable.writes)
    new_plan=preview(client,item,profile)
    assert all(p['action']=='unchanged' for p in new_plan['pages'])
    again=complete(client,item,start(client,item,new_plan))
    assert again['counts']['skipped']>=len(plan['pages']) and len(writable.writes)==count


def test_uncertain_create_reconciles_without_resending(client,writable):
    profile,item=setup(client);plan=preview(client,item,profile);job=start(client,item,plan)
    writable.fail='after_create'
    uncertain=advance(client,item,job)
    assert uncertain['status']=='uncertain' and len(writable.writes)==1
    refused=client.post(jobs_url(item)+'/'+job['id']+'/control',json={'expectedRevision':uncertain['revision'],'action':'abandon'})
    assert refused.status_code==409
    resumed=advance(client,item,uncertain)
    assert resumed['status']=='pending' and resumed['completed']==1 and len(writable.writes)==1
    complete(client,item,resumed)
    assert len(writable.pages)==len(plan['pages'])+1


def test_uncertain_upload_and_backend_restart_recover_frozen_bytes(client,writable):
    profile,item=setup(client,True);plan=preview(client,item,profile);job=start(client,item,plan)
    for _ in plan['pages']:job=advance(client,item,job)
    writable.fail='after_upload';job=advance(client,item,job)
    assert job['status']=='uncertain'
    count=len(writable.writes)
    # A fresh request/repository read resumes the persisted journal, without RAM state.
    job=client.get(jobs_url(item)+'/'+job['id']).json()
    job=advance(client,item,job)
    assert len(writable.writes)==count and job['status']=='pending'
    complete(client,item,job)


def test_stale_page_and_racing_update_never_overwrite_manual_content(client,writable):
    profile,item=setup(client);first=preview(client,item,profile)
    complete(client,item,start(client,item,first))
    root=first['pages'][0]
    with docs.connection() as conn:remote_id=conn.execute('SELECT remote_id FROM documentation_confluence_pages WHERE id=?',(root['destinationId'],)).fetchone()[0]
    current=writable.pages[remote_id]
    plan=preview(client,item,profile);job=start(client,item,plan)
    current['body']['storage']['value']='<p>Manual edit</p>';current['version']['number']+=1
    before=len(writable.writes);blocked=advance(client,item,job)
    assert blocked['status']=='conflict' and len(writable.writes)==before and 'Manual edit' in current['body']['storage']['value']
    client.post(jobs_url(item)+'/'+job['id']+'/control',json={'expectedRevision':blocked['revision'],'action':'abandon'})
    reviewed=preview(client,item,profile)
    replace=start(client,item,reviewed,replaceReviewedKeys=['root'])
    def race():current['version']['number']+=1;current['body']['storage']['value']='<p>Newer manual edit</p>'
    writable.before_write=race
    conflict=advance(client,item,replace)
    assert conflict['status']=='conflict' and 'Newer manual edit' in current['body']['storage']['value']


def test_keep_remote_decision_persists_and_does_not_upload_to_kept_page(client,writable):
    profile,item=setup(client,True);first=preview(client,item,profile)
    complete(client,item,start(client,item,first))
    with docs.connection() as conn:rid=conn.execute("SELECT remote_id FROM documentation_confluence_pages WHERE page_key='root'").fetchone()[0]
    writable.pages[rid]['version']['number']+=1;writable.pages[rid]['body']['storage']['value']='<p>Keep this manual introduction</p>'
    plan=preview(client,item,profile)
    count=len(writable.writes)
    job=complete(client,item,start(client,item,plan,keepRemoteKeys=['root']))
    assert job['counts']['kept'] and len(writable.writes)==count
    again=preview(client,item,profile)
    assert again['pages'][0]['action']=='keep'
    assert 'Keep this manual' in writable.pages[rid]['body']['storage']['value']


def test_audience_change_blocks_all_writes_and_start_requires_confirmation(client,writable):
    profile,item=setup(client);plan=preview(client,item,profile)
    response=client.post(jobs_url(item),json={'previewId':plan['id'],'expectedVersion':1,'audienceConfirmed':False})
    assert response.status_code==422
    job=start(client,item,plan);writable.acl_changed=True
    result=advance(client,item,job)
    assert result['status']=='conflict' and not writable.writes


def test_known_failure_pause_retry_and_optimistic_revision_checks(client,writable):
    profile,item=setup(client);plan=preview(client,item,profile);job=start(client,item,plan)
    writable.fail='forbidden';failed=advance(client,item,job)
    assert failed['status']=='failed'
    stale=client.post(jobs_url(item)+'/'+job['id']+'/advance',json={'expectedRevision':job['revision']})
    assert stale.status_code==409
    paused=client.post(jobs_url(item)+'/'+job['id']+'/control',json={'expectedRevision':failed['revision'],'action':'pause'}).json()
    assert paused['status']=='paused'
    complete(client,item,paused)


def test_destination_lock_and_read_source_permissions(client,writable):
    profile,item=setup(client,True);plan=preview(client,item,profile);job=start(client,item,plan)
    second=preview(client,item,profile)
    assert client.post(jobs_url(item),json={'previewId':second['id'],'expectedVersion':1,'audienceConfirmed':True}).status_code==409
    auth_db.create_role('publish-no-inventory',['documentation.read','documentation.publish'])
    auth_db.create_user('job-publisher',auth.hash_password('Password123'),role='publish-no-inventory')
    client.post('/api/auth/login',json={'username':'job-publisher','password':'Password123'})
    assert client.get(jobs_url(item)+'/'+job['id']).status_code==403
    assert client.post(jobs_url(item)+'/'+job['id']+'/advance',json={'expectedRevision':job['revision']}).status_code==403
    assert not writable.writes


def test_audit_failure_after_write_leaves_durable_send_marker_for_recovery(client,writable):
    profile,item=setup(client);plan=preview(client,item,profile);job=start(client,item,plan)
    with docs.connection(True) as conn:conn.execute("CREATE TRIGGER fail_publication_result BEFORE INSERT ON documentation_confluence_audit WHEN NEW.action='publication_step' BEGIN SELECT RAISE(ABORT,'audit failed'); END")
    with pytest.raises(sqlite3.IntegrityError):advance(client,item,job)
    assert len(writable.writes)==1
    with docs.connection(True) as conn:
        conn.execute('DROP TRIGGER fail_publication_result');conn.execute('UPDATE documentation_confluence_jobs SET lease_until=0 WHERE id=?',(job['id'],))
    current=client.get(jobs_url(item)+'/'+job['id']).json();resumed=advance(client,item,current)
    assert resumed['completed']==1 and len(writable.writes)==1
    complete(client,item,resumed)


def new_local_version(client,item):
    current=client.get(ROOT+f"/{item['id']}").json()
    draft=client.post(ROOT+f"/{item['id']}/transition",json={'expectedVersion':current['version'],'action':'draft'}).json()
    saved=client.put(ROOT+f"/{item['id']}",json={**draft['form'],'notes':'New reviewed content','expectedVersion':draft['version']}).json()
    return publish(client,saved)


def test_versioned_updates_and_uncertain_put_reconciliation(client,writable):
    profile,item=setup(client);complete(client,item,start(client,item,preview(client,item,profile)))
    item=new_local_version(client,item)
    response=client.post(API+f"/documents/{item['id']}/versions/2/previews",json={'profileId':profile['id'],'expectedVersion':1})
    assert response.status_code==201,response.text
    plan=response.json();job=start(client,item,plan,2)
    writable.fail='after_update';uncertain=advance(client,item,job,2)
    assert uncertain['status']=='uncertain'
    count=len(writable.writes);job=advance(client,item,uncertain,2)
    assert job['completed']==1 and len(writable.writes)==count
    complete(client,item,job,2)
    assert any(r.method=='PUT' for r in writable.writes)


def test_preserved_page_can_be_replaced_only_after_new_review(client,writable):
    profile,item=setup(client);first=preview(client,item,profile);complete(client,item,start(client,item,first))
    with docs.connection() as conn:identifier=conn.execute("SELECT remote_id FROM documentation_confluence_pages WHERE page_key='root'").fetchone()[0]
    writable.pages[identifier]['version']['number']+=1;writable.pages[identifier]['body']['storage']['value']='<p>Manual introduction</p>'
    plan=preview(client,item,profile);complete(client,item,start(client,item,plan,keepRemoteKeys=['root']))
    kept=preview(client,item,profile);assert kept['pages'][0]['action']=='keep'
    complete(client,item,start(client,item,kept,replaceReviewedKeys=['root']))
    assert '<p>Manual introduction</p>' not in writable.pages[identifier]['body']['storage']['value']
    with docs.connection() as conn:assert conn.execute("SELECT preserve_remote FROM documentation_confluence_pages WHERE page_key='root'").fetchone()[0]==0


def test_rate_limit_cannot_retry_early_and_profile_credentials_can_be_revalidated(client,writable):
    profile,item=setup(client);plan=preview(client,item,profile);job=start(client,item,plan)
    writable.fail='rate_limit';limited=advance(client,item,job)
    assert limited['status']=='failed' and limited['retryAt']>time.time()
    assert client.post(jobs_url(item)+'/'+job['id']+'/advance',json={'expectedRevision':limited['revision']}).status_code==409
    settings={k:v for k,v in profile.items() if k in ('name','baseUrl','spaceKey','parentPageId','authMode','caPem','timeoutSeconds','enabled')}
    update=client.put(API+f"/profiles/{profile['id']}",json={**settings,'expectedVersion':1,'token':TOKEN}).json()
    assert update['version']==2
    response=client.post(jobs_url(item)+'/'+job['id']+'/revalidate',json={'expectedRevision':limited['revision'],'expectedProfileVersion':2,'audienceConfirmed':True})
    assert response.status_code==200,response.text
    with docs.connection(True) as conn:conn.execute('UPDATE documentation_confluence_jobs SET retry_at=0 WHERE id=?',(job['id'],))
    complete(client,item,response.json())


def test_uncertain_unapplied_create_requires_explicit_manual_reset(client,writable):
    profile,item=setup(client);job=start(client,item,preview(client,item,profile))
    # Simulate a backend crash after persisting a send marker but before any HTTP request.
    with docs.connection(True) as conn:
        conn.execute("UPDATE documentation_confluence_steps SET status='inflight',sent=1 WHERE job_id=? AND ordinal=0",(job['id'],))
        conn.execute("UPDATE documentation_confluence_jobs SET status='running' WHERE id=?",(job['id'],))
    unknown=advance(client,item,job)
    assert unknown['status']=='uncertain' and not writable.writes
    response=client.post(jobs_url(item)+'/'+job['id']+'/resolve',json={'expectedRevision':unknown['revision'],'notAppliedConfirmed':True})
    assert response.status_code==200,response.text
    complete(client,item,response.json())
    assert len(writable.pages)==6  # homepage plus the switch template hierarchy


def test_concurrent_advances_have_one_durable_owner_and_one_remote_write(client,writable):
    from concurrent.futures import ThreadPoolExecutor
    profile,item=setup(client);job=start(client,item,preview(client,item,profile))
    def send(_):return client.post(jobs_url(item)+'/'+job['id']+'/advance',json={'expectedRevision':job['revision']}).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:statuses=sorted(executor.map(send,range(2)))
    assert statuses==[200,409] and len(writable.writes)==1


def test_publication_jobs_and_mutations_do_not_cross_tenants(client,writable):
    profile,item=setup(client);job=start(client,item,preview(client,item,profile))
    auth_db.create_user('publication-admin',auth.hash_password('Password123'),role='admin')
    client.post('/api/auth/login',json={'username':'publication-admin','password':'Password123'})
    other=client.post('/api/tenants',json={'name':'Other publication tenant'}).json()['id']
    headers={'X-Tenant-ID':other}
    assert client.get(jobs_url(item)+'/'+job['id'],headers=headers).status_code==404
    assert client.post(jobs_url(item)+'/'+job['id']+'/advance',json={'expectedRevision':job['revision']},headers=headers).status_code==404
    assert not writable.writes
