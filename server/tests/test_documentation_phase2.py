"""Offline assets must use frozen source data, portable links and retained grants."""
import copy
import hashlib
import io
import json
import posixpath
import re
import zipfile
from xml.etree import ElementTree as ET
import pytest
from PIL import Image
import auth
import auth_db
from documentation import exports,diagrams,repository as repo
from tests.test_dc_inventory import device,dc,rack
from tests.test_dc_connections import connect
from tests.test_inventory_ipam import subnet,address_port
from tests.test_documentation_phase1 import ROOT,make,publish


def package(response):
    assert response.status_code==200,response.text
    return zipfile.ZipFile(io.BytesIO(response.content))


def check_links(archive):
    """Every generated relative file/anchor target resolves without the app."""
    names=set(archive.namelist())
    for path in names:
        if not path.endswith('.md'):continue
        content=archive.read(path).decode()
        for target in re.findall(r'\]\(([^\s)]+)\)',content):
            if target.startswith(('https://','http://')):continue
            file,_,anchor=target.partition('#')
            destination=posixpath.normpath(posixpath.join(posixpath.dirname(path),file)) if file else path
            assert destination in names,(path,target)
            if anchor:assert f'id="{anchor}"' in archive.read(destination).decode(),(path,target)


def test_phase2_offline_diagrams_links_checksums_and_immutable_assets(client,monkeypatch):
    center=dc(client);r1=rack(client,center);r2=rack(client,center,name='Other rack')
    subnet(client,'10.30.40.0/24')
    a=address_port(client,device(client,'Zażółć | <core>',rackId=r1['id'],rackPosition=1,heightU=1),'10.30.40.1/24')
    b=device(client,'Outside peer',rackId=r2['id'],rackPosition=3,heightU=1)
    cable=connect(client,a,b,label='Uplink [A] <B>').json()
    item=publish(client,make(client,scopeSpec={'kind':'rack','id':r1['id']}))
    root=f"{ROOT}/{item['id']}/versions/1"
    saved=client.get(root).json()
    assert saved['document']['rendererVersion']==3
    assets=saved['document']['assets']
    assert {'physical','connections','equipment','logical'}<={a['chapter'] for a in assets}
    response=client.get(root+'/export?format=zip')
    with package(response) as archive:
        manifest=json.loads(archive.read('manifest.json'))
        assert manifest['scope']['id']==r1['id']
        assert manifest['diagramRendering']['layoutSha256']
        assert set(archive.namelist())-{r['path'] for r in manifest['files']}=={'manifest.json'}
        for record in manifest['files']:
            assert record['sha256']==hashlib.sha256(archive.read(record['path'])).hexdigest()
        for asset in assets:
            image=Image.open(io.BytesIO(archive.read(asset['files']['png'])))
            assert image.format=='PNG' and image.width==1120 and image.height<4096
            assert len(image.getcolors(image.width*image.height))>10
            svg=archive.read(asset['files']['svg'])
            ET.fromstring(svg)
            assert b'<script' not in svg and b'http://' not in svg.replace(b'http://www.w3.org/2000/svg',b'')
        detail=next(a for a in assets if a['id']==f"connection-{cable['id']}")
        assert b'outside document scope' in archive.read(detail['files']['svg'])
        refs=archive.read('documents/references.md').decode()
        assert 'Outside document scope' in refs and 'Outside peer' in refs
        check_links(archive)
        path=detail['files']['png'];frozen=archive.read(path)
    standalone=client.get(root+'/export?format=md')
    assert b'../assets/' not in standalone.content
    assert hashlib.sha256(standalone.content).hexdigest()==saved['sha256']==manifest['standaloneMarkdownSha256']
    endpoint=root+'/assets/'+path.split('/')[-1]
    assert client.get(endpoint).content==frozen
    assert client.get(endpoint).headers['content-type']=='image/png'
    assert client.get(root+'/assets/not-in-this-version.png').status_code==404
    assert client.get(root+'/assets/..%2Fmanifest.json').status_code in (404,422)
    with repo.connection(True) as conn:
        conn.execute("UPDATE dv_devices SET name='Changed after publication' WHERE id=?",(a['id'],))
    def fail(*args):raise AssertionError('Historical download must not render or collect live data')
    monkeypatch.setattr(diagrams,'generate',fail)
    assert client.get(endpoint).content==frozen
    assert client.get(root+'/export?format=zip').content==response.content
    auth_db.create_role('phase2-doc-only',['documentation'])
    auth_db.create_user('phase2-user',auth.hash_password('Password123'),role='phase2-doc-only')
    client.post('/api/auth/login',json={'username':'phase2-user','password':'Password123'})
    assert client.get(endpoint).status_code==403


def test_phase2_large_tables_are_lossless_and_links_resolve():
    rows=[[f'row {i}','=2+3' if i==0 else 'Zażółć | [x]\nsecond line'] for i in range(237)]
    document={'id':7,'version':1,'form':{'title':'Portable','dcName':'Test'},
              'snapshot':{'tables':[{'id':'../../unsafe table','title':'Large table','chapter':'general','columns':['ID','Value'],'rows':rows}]}}
    first=exports.artifacts(copy.deepcopy(document),1,'2026-10-19T00:00:00Z','')
    assert first==exports.artifacts(copy.deepcopy(document),1,'2026-10-19T00:00:00Z','')
    content,zip_bytes,digest=first
    assert b'row 236' in content
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        assert all(not name.startswith('/') and '..' not in name.split('/') for name in archive.namelist())
        tables=[n for n in archive.namelist() if re.search(r'-[123]\.md$',n)]
        assert len(tables)==3
        assert sum(len(re.findall(r'^\| row ',archive.read(n).decode(),re.M)) for n in tables)==237
        assert b'row 236' not in archive.read('documents/dc-7.md')
        csv=next(n for n in archive.namelist() if n.endswith('.csv'))
        assert "'=2+3" in archive.read(csv).decode('utf-8-sig')
        check_links(archive)
    assert digest==hashlib.sha256(content).hexdigest()


def test_phase2_render_failure_is_atomic_and_actionable(client,monkeypatch):
    a=device(client,'Router')
    item=make(client,templateId='switch',scopeSpec={'kind':'device','id':a['id']})
    def missing(*args,**kwargs):raise FileNotFoundError('node')
    monkeypatch.setattr(diagrams.subprocess,'run',missing)
    response=client.post(f"{ROOT}/{item['id']}/versions",json={'expectedVersion':1})
    assert response.status_code==422 and 'Node.js' in response.text
    assert client.get(f"{ROOT}/{item['id']}/versions").json()['total']==0
    assert not any(e['action']=='create_version' for e in client.get(f"{ROOT}/{item['id']}/history").json()['items'])


def test_phase2_same_snapshot_gives_identical_images_and_zip(client):
    center=dc(client);cabinet=rack(client,center)
    device(client,'Core',rackId=cabinet['id'],rackPosition=1,heightU=1)
    item=make(client,scopeSpec={'kind':'rack','id':cabinet['id']})
    captured={'id':item['id'],'version':1,'form':item['form'],'snapshot':item['snapshot']}
    first=exports.artifacts(copy.deepcopy(captured),1,'2026-10-19T00:00:00Z','')
    assert first==exports.artifacts(copy.deepcopy(captured),1,'2026-10-19T00:00:00Z','')


def test_phase2_historical_snapshot_without_geometry_remains_exportable():
    document={'id':1,'version':1,'form':{'title':'Legacy','dcName':'DC'},'snapshot':{'tables':[], 'sources':[]}}
    content,blob,_=exports.artifacts(document,1,'2026-10-19','')
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        assert not any(n.endswith('.png') for n in archive.namelist())
        assert 'refresh a draft' in json.loads(archive.read('manifest.json'))['limitations'][-1]
    assert b'Legacy' in content


def test_phase2_missing_references_and_literal_code_delimiters():
    value="\\| `code` [click](file) *bold* _italic_"
    document={'id':3,'version':1,'form':{'title':'Missing','dcName':'DC'},'snapshot':{'tables':[
        {'id':'missing','title':'Missing reference','chapter':'general','columns':['Device'],
         'rows':[[value]],'rowReferences':[{'module':'device-visualization','type':'device','id':999}]}]}}
    content,blob,_=exports.artifacts(document,1,'2026-10-19','')
    assert b'&#92;\\| &#96;code&#96;' in content
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        check_links(archive)
        assert b'Source reference is missing' in archive.read('documents/references.md')
