import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import pytest
import auth
import auth_db
import db
from documentation import repository as repo,sources
from tests.test_dc_inventory import device,dc,rack
from tests.test_dc_connections import connect
from tests.test_inventory_ipam import subnet,address_port
from tests.test_dhcp_generator import create as dhcp_create,publish as dhcp_publish
ROOT='/api/documentation/dc'


def make(client,**values):
    result=client.post(ROOT,json={'title':'DC documentation','dcName':'DC1','ownerTeam':'Network team','purpose':'Operate the site',**values})
    assert result.status_code==201,result.text
    return result.json()


def move(client,item,action,**extra):
    result=client.post(f"{ROOT}/{item['id']}/transition",json={'expectedVersion':item['version'],'action':action,**extra})
    assert result.status_code==200,result.text
    return result.json()


def publish(client,item):return move(client,move(client,item,'submit'),'publish',description='Reviewed baseline')


def test_review_publication_comparison_restore_and_history(client):
    item=make(client)
    root=f"{ROOT}/{item['id']}"
    assert client.post(root+'/transition',json={'expectedVersion':1,'action':'publish'}).status_code==409
    review=move(client,item,'submit')
    assert review['status']=='review'
    assert client.put(root,json={**review['form'],'expectedVersion':review['version']}).status_code==409
    assert client.post(root+'/versions',json={'expectedVersion':review['version']}).status_code==409
    published=move(client,review,'publish')
    assert published['status']=='published' and published['publishedVersion']==1
    first=client.get(root+'/versions/1').json()
    assert first['kind']=='published' and first['document']['status']=='published'
    original=client.get(root+'/versions/1/export').content
    draft=move(client,published,'draft')
    saved=client.put(root,json={**draft['form'],'notes':'Changed recovery reference','expectedVersion':draft['version']}).json()
    published=publish(client,saved)
    diff=client.get(root+'/compare?before=1&after=2').json()
    assert diff['changedFields']==['notes'] and 'Changed recovery reference' in diff['diff']
    assert client.get(root+'/versions/1/export').content==original
    assert client.post(root+'/versions/1/restore',json={'expectedVersion':published['version']}).status_code==409
    draft=move(client,published,'draft')
    restored=client.post(root+'/versions/1/restore',json={'expectedVersion':draft['version']})
    assert restored.status_code==200 and restored.json()['form']['notes']==''
    assert restored.json()['status']=='draft'
    assert client.get(root+'/versions/1/export').content==original
    actions=[row['action'] for row in client.get(root+'/history').json()['items']]
    assert 'publish' in actions and 'restore' in actions and 'transition' in actions
    assert client.get(ROOT+'?status=published').json()['total']==0
    assert client.get(ROOT+'?status=draft&template=network').json()['total']==1


@pytest.mark.parametrize('template',['network','switch','firewall','runbook'])
def test_four_templates_and_required_review_content(client,template):
    item=make(client,templateId=template,dcName='' if template=='runbook' else 'Subject',purpose='',ownerTeam='')
    blocked=client.post(f"{ROOT}/{item['id']}/transition",json={'expectedVersion':1,'action':'submit'})
    assert blocked.status_code==422 and blocked.json()['detail']['validation']['blocking']
    notes={'steps':'1. Check the service','verification':'Check connectivity','rollback':'Restore previous configuration'} if template=='runbook' else {}
    form={**item['form'],'purpose':'Documented service','ownerTeam':'Operations','templateNotes':notes}
    saved=client.put(f"{ROOT}/{item['id']}",json={**form,'expectedVersion':1}).json()
    result=publish(client,saved)
    version=client.get(f"{ROOT}/{item['id']}/versions/{result['publishedVersion']}").json()
    labels=[page['label'] for page in version['document']['chapters']]
    assert len(labels)>=3
    assert ('Policy and NAT references' in labels)==(template=='firewall')
    if template=='runbook':
        content=client.get(f"{ROOT}/{item['id']}/versions/1/export").text
        assert 'Check connectivity' in content and 'Restore previous configuration' in content


def test_consistent_adapters_dc_inventory_ipam_routing_dhcp_and_external_peer(client):
    center=dc(client);cabinet=rack(client,center);other=rack(client,center,name='Rack B')
    network=subnet(client,'10.20.3.0/24')
    a=address_port(client,device(client,'Core-A',rackId=cabinet['id'],rackPosition=1,heightU=1),'10.20.3.1/24')
    b=device(client,'Peer-B',rackId=other['id'],rackPosition=2,heightU=1)
    assert connect(client,a,b,label='Uplink').status_code==201
    db.save_host('Core-A',[{'network':'10.20.3.0/24','nextHop':'directly connected','interface':'eth0'}],[{'name':'eth0','ipAddress':'10.20.3.1/24','description':'LAN'}])
    dhcp=dhcp_create(client);version=dhcp_publish(client,dhcp).json()
    scope={'kind':'rack','id':cabinet['id'],'dhcpVersionIds':[version['id']]}
    preview=client.post(ROOT+'/coverage',json={'templateId':'network','scopeSpec':scope})
    assert preview.status_code==200,preview.text
    item=make(client,scopeSpec=scope)
    snapshot=item['snapshot'];tables={t['id']:t for t in snapshot['tables']}
    assert tables['devices']['rows'][0][0]=='Core-A'
    assert len(tables['devices']['rows'])==1
    assert tables['connections']['rows'][0][-1] is True
    assert tables['subnets']['rows'][0][0]=='10.20.3.0/24'
    interfaces=next(t for t in snapshot['tables'] if t['id'].startswith('interfaces-'))
    assert interfaces['rows'][0][1]=='10.20.3.1/24'
    assert 'dhcp-'+version['id'] in tables
    assert {'device-visualization','dc-inventory','ipam.read','routing-map','dhcp-generator'}==set(snapshot['requiredPermissions'])
    assert any(s['type']=='external-device' and s['id']==b['id'] for s in snapshot['sources'])
    assert any(s['type']=='subnet' and s['id']==network['id'] for s in snapshot['sources'])
    assert client.get(ROOT+'/options?kind=dhcp').json()['items'][0]['id']==version['id']
    result=publish(client,item)
    exported=client.get(f"{ROOT}/{item['id']}/versions/{result['publishedVersion']}/export").text
    assert '| Core-A |' in exported and 'Routing Map: Core-A' in exported
    assert 'Source provenance' in exported and 'Uplink' in exported


def test_refresh_requires_preview_and_preserves_narrative_and_old_revision(client):
    a=device(client,'Core-A')
    item=make(client,templateId='switch',scopeSpec={'kind':'device','id':a['id']},notes='Keep this text')
    root=f"{ROOT}/{item['id']}"
    assert client.post(root+'/versions',json={'expectedVersion':1}).status_code==201
    original=client.get(root+'/versions/1/export').content
    with repo.connection(True) as conn:conn.execute("UPDATE dv_devices SET name='Renamed',version=version+1 WHERE id=?",(a['id'],))
    preview=client.post(root+'/refresh/preview',json={'expectedVersion':1}).json()
    assert preview['changes']
    with repo.connection(True) as conn:conn.execute("UPDATE dv_devices SET model='New model',version=version+1 WHERE id=?",(a['id'],))
    stale=client.post(root+'/refresh',json={'expectedVersion':1,'snapshotDigest':preview['snapshot']['digest']})
    assert stale.status_code==409
    assert client.get(root).json()['version']==1
    preview=client.post(root+'/refresh/preview',json={'expectedVersion':1}).json()
    refreshed=client.post(root+'/refresh',json={'expectedVersion':1,'snapshotDigest':preview['snapshot']['digest']})
    assert refreshed.status_code==200,refreshed.text
    assert refreshed.json()['form']['notes']=='Keep this text'
    assert refreshed.json()['version']==2
    assert client.get(root+'/versions/1/export').content==original
    assert client.get(root+'/versions/1').json()['document']['snapshot']['tables'][1]['rows'][0][0]=='Core-A'


def test_source_permissions_remain_enforced_for_saved_documents_and_revisions(client):
    a=device(client,'Private switch')
    item=publish(client,make(client,templateId='switch',scopeSpec={'kind':'device','id':a['id']}))
    root=f"{ROOT}/{item['id']}"
    auth_db.create_role('documentation-only',['documentation'])
    auth_db.create_user('doc-only',auth.hash_password('Password123'),role='documentation-only')
    client.post('/api/auth/login',json={'username':'doc-only','password':'Password123'})
    assert client.get(ROOT).json()['total']==0
    for path in ('','/versions','/versions/1','/versions/1/export','/history'):
        assert client.get(root+path).status_code==403
    assert client.post(root+'/refresh/preview',json={'expectedVersion':item['version']}).status_code==403
    client.post('/api/auth/logout')
    auth_db.create_role('docs-reader',['documentation.read','device-visualization','dc-inventory'])
    auth_db.create_user('docs-reader',auth.hash_password('Password123'),role='docs-reader')
    client.post('/api/auth/login',json={'username':'docs-reader','password':'Password123'})
    assert client.get(root).status_code==200
    assert client.get(root+'/versions/1/export').status_code==200
    assert client.post(root+'/transition',json={'expectedVersion':item['version'],'action':'draft'}).status_code==403
    assert client.post(ROOT,json={'title':'Denied','dcName':'DC'}).status_code==403


def test_granular_editor_cannot_publish_and_publish_is_concurrency_safe(client):
    item=move(client,make(client),'submit')
    root=f"{ROOT}/{item['id']}"
    auth_db.create_role('docs-editor',['documentation.read','documentation.write'])
    auth_db.create_user('docs-editor',auth.hash_password('Password123'),role='docs-editor')
    client.post('/api/auth/login',json={'username':'docs-editor','password':'Password123'})
    assert client.post(root+'/transition',json={'expectedVersion':item['version'],'action':'publish'}).status_code==403
    client.post('/api/auth/logout')
    def attempt(_):
        try:repo.transition(item['id'],item['version'],'publish','',None);return 'published'
        except repo.Conflict:return 'stale'
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(attempt,range(2)))==['published','stale']
    assert repo.versions(item['id'],20,0)['total']==1


def test_oversized_scope_and_publish_failure_are_atomic(client,monkeypatch):
    a=device(client)
    previous_limit=sources.MAX_ROWS
    monkeypatch.setattr(sources,'MAX_ROWS',1)
    failed=client.post(ROOT,json={'title':'Oversized','dcName':'DC','scopeSpec':{'kind':'device','id':a['id']}})
    assert failed.status_code==422
    assert client.get(ROOT).json()['total']==0
    monkeypatch.setattr(sources,'MAX_ROWS',previous_limit)
    item=move(client,make(client),'submit')
    original=repo.log
    def fail(conn,identifier,actor,action,old,new):
        if action=='transition':raise RuntimeError('Audit unavailable')
        return original(conn,identifier,actor,action,old,new)
    monkeypatch.setattr(repo,'log',fail)
    with pytest.raises(RuntimeError):repo.transition(item['id'],item['version'],'publish','',None)
    assert repo.get(item['id'])['status']=='review'
    assert repo.versions(item['id'],20,0)['total']==0


def test_additive_migration_preserves_legacy_forms_and_frozen_bytes(monkeypatch,tmp_path):
    path=tmp_path/'legacy-documentation.db'
    monkeypatch.setattr(db,'DB_PATH',str(path))
    conn=sqlite3.connect(path)
    conn.executescript('''
      CREATE TABLE documentation_dc_forms(id INTEGER PRIMARY KEY,title TEXT NOT NULL,dc_name TEXT NOT NULL,payload TEXT NOT NULL,
        version INTEGER NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
      CREATE TABLE documentation_dc_form_audit(id INTEGER PRIMARY KEY,document_id INTEGER NOT NULL,actor_id INTEGER,action TEXT NOT NULL,
        old_payload TEXT,new_payload TEXT NOT NULL,created_at TEXT NOT NULL);
      CREATE TABLE documentation_dc_versions(id INTEGER PRIMARY KEY,document_id INTEGER NOT NULL,number INTEGER NOT NULL,draft_version INTEGER NOT NULL,
        payload TEXT NOT NULL,description TEXT NOT NULL,actor_id INTEGER,actor_name TEXT,created_at TEXT NOT NULL,
        markdown BLOB NOT NULL,artifact BLOB NOT NULL,sha256 TEXT NOT NULL,UNIQUE(document_id,number),UNIQUE(document_id,draft_version));
    ''')
    form={'title':'Legacy document','dcName':'Legacy DC','power':'Retained power data'}
    document={'id':1,'form':form,'version':5}
    conn.execute('INSERT INTO documentation_dc_forms VALUES(1,?,?,?,?,?,?)',(form['title'],form['dcName'],json.dumps(form),7,'2026-01-01','2026-01-02'))
    conn.execute('INSERT INTO documentation_dc_versions VALUES(1,1,1,5,?,?,NULL,NULL,?,?,?,?)',
                 (json.dumps(document),'Legacy baseline','2026-01-01',b'historical markdown',b'historical archive','old-hash'))
    conn.commit();conn.close()
    repo.init_db();repo.init_db()
    assert repo.get(1)['form']==form
    assert repo.get(1)['status']=='draft' and repo.get(1)['version']==7
    assert repo.get_version(1,1)['kind']=='saved'
    assert repo.download(1,1,'md',None)==b'historical markdown'
    assert repo.download(1,1,'zip',None)==b'historical archive'
    assert repo.create_version(1,7,'New baseline',None)['number']==2
    assert repo.download(1,1,'md',None)==b'historical markdown'
