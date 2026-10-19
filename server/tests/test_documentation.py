import pytest
import sqlite3
import auth
import auth_db
from documentation import repository as repo

ROOT='/api/documentation/dc'


def test_dc_form_save_reopen_update_and_conflict(client):
    payload={'title':'DC Warsaw documentation','dcName':'DC Warsaw','ownerTeam':'Network operations',
             'power':'Dual A/B feeds','emergencyContact':'NOC +48 123456789','reviewDate':'2027-01-15'}
    created=client.post(ROOT,json=payload)
    assert created.status_code==201,created.text
    record=created.json()
    assert record['form']['power']==payload['power']
    assert client.get(f"{ROOT}/{record['id']}").json()==record
    assert client.get(ROOT).json()['total']==1
    update={**record['form'],'power':'A/B feeds and UPS','expectedVersion':record['version']}
    saved=client.put(f"{ROOT}/{record['id']}",json=update)
    assert saved.status_code==200,saved.text
    assert saved.json()['version']==2
    assert client.put(f"{ROOT}/{record['id']}",json=update).status_code==409
    assert client.get(f"{ROOT}/{record['id']}").json()['form']['power']=='A/B feeds and UPS'
    with repo.connection() as conn:
        assert [r[0] for r in conn.execute('SELECT action FROM documentation_dc_form_audit ORDER BY id')]==['create','update']


@pytest.mark.parametrize('payload',[
 {'title':'','dcName':'DC'}, {'title':'Documentation','dcName':'  '},
 {'title':'Documentation','dcName':'DC','reviewDate':'2026-02-30'},
 {'title':'Documentation','dcName':'DC','environment':'invented'},
 {'title':'Documentation','dcName':'DC','inventorySource':42},
])
def test_dc_form_validation_does_not_persist(client,payload):
    assert client.post(ROOT,json=payload).status_code==422
    assert client.get(ROOT).json()['total']==0


def test_dc_form_audit_failure_rolls_back(client,monkeypatch):
    original=repo.detail
    def fail_after_insert(*args):raise RuntimeError('Readback failed')
    monkeypatch.setattr(repo,'detail',fail_after_insert)
    with pytest.raises(RuntimeError):repo.save({'title':'Rollback','dcName':'DC'},None)
    monkeypatch.setattr(repo,'detail',original)
    assert client.get(ROOT).json()['total']==0
    with repo.connection() as conn:assert conn.execute('SELECT COUNT(*) FROM documentation_dc_form_audit').fetchone()[0]==0


def test_dc_form_permissions_and_tenant_isolation(client):
    record=client.post(ROOT,json={'title':'DC documentation','dcName':'DC'}).json()
    auth_db.create_role('no-docs',['dc-inventory'])
    auth_db.create_user('without-docs',auth.hash_password('Password123'),role='no-docs')
    client.post('/api/auth/login',json={'username':'without-docs','password':'Password123'})
    assert client.get(ROOT).status_code==403
    assert client.get(f"{ROOT}/{record['id']}").status_code==403
    assert client.post(ROOT,json={'title':'Denied','dcName':'DC'}).status_code==403
    client.post('/api/auth/logout')
    auth_db.create_user('dc-doc-admin',auth.hash_password('Password123'),role='admin')
    client.post('/api/auth/login',json={'username':'dc-doc-admin','password':'Password123'})
    other=client.post('/api/tenants',json={'name':'Other DC'}).json()['id']
    assert client.get(ROOT,headers={'X-Tenant-ID':other}).json()['total']==0
    assert client.get(f"{ROOT}/{record['id']}",headers={'X-Tenant-ID':other}).status_code==404


def test_dc_chapter_drafts_preserve_existing_forms_and_save_all_sections(client):
    old=client.post(ROOT,json={'title':'Existing DC','dcName':'DC1','power':'Original A/B description'}).json()
    chapters={'floorPlans':'Drawing DC1-01','equipmentScope':'Core and storage','patchPanels':'PP-A',
              'routingDesign':'Two routing domains','carrierCircuits':'Circuit ABC','powerDistribution':'PDU A/B',
              'nameAddressServices':'Internal DNS','haDesign':'Dual core','supportLifecycle':'Support ref 123'}
    response=client.put(f"{ROOT}/{old['id']}",json={**old['form'],**chapters,'expectedVersion':old['version']})
    assert response.status_code==200,response.text
    saved=client.get(f"{ROOT}/{old['id']}").json()
    assert saved['form']['power']=='Original A/B description'
    for key,value in chapters.items():assert saved['form'][key]==value
    assert saved['form']['loggingServices']==''


def test_immutable_versions_markdown_zip_and_draft_changes(client,monkeypatch):
    import hashlib
    import io
    import json
    import zipfile
    from documentation import exports
    record=client.post(ROOT,json={'title':'DC <Warsaw>','dcName':'DC1','power':'A/B feeds',
                                 'notes':'<script>bad</script>\n```text\n<script>example</script>\n```'}).json()
    root=f"{ROOT}/{record['id']}"
    created=client.post(root+'/versions',json={'expectedVersion':1,'description':'Initial baseline'})
    assert created.status_code==201,created.text
    version=created.json()
    assert version['number']==1 and version['document']['form']['power']=='A/B feeds'
    assert len(version['document']['chapters'])==11
    md=client.get(root+'/versions/1/export?format=md')
    archive=client.get(root+'/versions/1/export?format=zip')
    assert md.status_code==archive.status_code==200
    assert '&lt;script&gt;bad&lt;/script&gt;' in md.text
    assert '\n<script>example</script>\n' in md.text
    assert '## Logical network' in md.text and 'Not recorded.' in md.text
    assert 'private, no-store'==md.headers['cache-control']
    with zipfile.ZipFile(io.BytesIO(archive.content)) as package:
        assert set(package.namelist())=={'README.md','manifest.json',f"documents/dc-{record['id']}.md"}
        manifest=json.loads(package.read('manifest.json'))
        assert manifest['files'][0]['sha256']==hashlib.sha256(md.content).hexdigest()==version['sha256']
        assert package.read(manifest['files'][0]['path'])==md.content
    updated=client.put(root,json={**record['form'],'power':'New power','expectedVersion':1}).json()
    assert client.post(root+'/versions',json={'expectedVersion':updated['version']}).status_code==201
    assert client.get(root+'/versions?limit=1').json()['total']==2
    assert client.get(root+'/versions?limit=1&offset=1').json()['versionForCurrentDraft']==2
    # Downloads use frozen bytes even if the renderer is later changed or unavailable.
    def fail(*args):raise RuntimeError('Renderer must not run for historical export')
    monkeypatch.setattr(exports,'artifacts',fail)
    monkeypatch.setattr(exports,'CATALOG',[])
    assert client.get(root+'/versions/1/export?format=md').content==md.content
    assert client.get(root+'/versions/1/export?format=zip').content==archive.content
    assert client.get(root+'/versions/1').json()['document']['form']['power']=='A/B feeds'
    assert len(client.get(root+'/versions/1').json()['document']['chapters'])==11
    with repo.connection(True) as conn:
        with pytest.raises(sqlite3.IntegrityError):conn.execute('UPDATE documentation_dc_versions SET description=?',('changed',))
        with pytest.raises(sqlite3.IntegrityError):conn.execute('DELETE FROM documentation_dc_versions')


def test_version_concurrency_parent_scoping_and_rollback(client,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    record=client.post(ROOT,json={'title':'DC','dcName':'DC1'}).json()
    identifier=record['id']
    def create(_):
        try:repo.create_version(identifier,1,'',None);return 'created'
        except repo.VersionExists:return 'duplicate'
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(create,range(2)))==['created','duplicate']
    assert client.post(f'{ROOT}/{identifier}/versions',json={'expectedVersion':99}).status_code==409
    other=client.post(ROOT,json={'title':'Other','dcName':'DC2'}).json()
    assert client.get(f"{ROOT}/{other['id']}/versions/1").status_code==404
    assert client.get(f"{ROOT}/{other['id']}/versions/1/export").status_code==404
    def fail(*args):raise RuntimeError('Readback failed')
    monkeypatch.setattr(repo,'version_detail',fail)
    with pytest.raises(RuntimeError):repo.create_version(other['id'],1,'',None)
    assert repo.versions(other['id'],20,0)['total']==0
    with repo.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM documentation_dc_form_audit WHERE document_id=? AND action='create_version'",(other['id'],)).fetchone()[0]==0


def test_version_permissions_and_tenants(client):
    record=client.post(ROOT,json={'title':'Private DC','dcName':'DC1'}).json()
    root=f"{ROOT}/{record['id']}"
    assert client.post(root+'/versions',json={'expectedVersion':1}).status_code==201
    auth_db.create_role('no-versions',['dc-inventory'])
    auth_db.create_user('no-versions',auth.hash_password('Password123'),role='no-versions')
    client.post('/api/auth/login',json={'username':'no-versions','password':'Password123'})
    for path in ('/versions','/versions/1','/versions/1/export?format=zip'):
        assert client.get(root+path).status_code==403
    assert client.post(root+'/versions',json={'expectedVersion':1}).status_code==403
    client.post('/api/auth/logout')
    auth_db.create_user('version-admin',auth.hash_password('Password123'),role='admin')
    client.post('/api/auth/login',json={'username':'version-admin','password':'Password123'})
    tenant=client.post('/api/tenants',json={'name':'Version tenant'}).json()['id']
    for path in ('/versions','/versions/1','/versions/1/export?format=zip'):
        assert client.get(root+path,headers={'X-Tenant-ID':tenant}).status_code==404


def test_chapter_catalog_matches_validated_schema():
    from documentation.exports import CATALOG
    from documentation.schemas import DCForm
    fields=[field['id'] for page in CATALOG for section in page['sections'] for field in section['fields']]
    assert len(fields)==len(set(fields))
    assert set(fields)==set(DCForm.model_fields)-{'templateId','scopeSpec','templateNotes'}
