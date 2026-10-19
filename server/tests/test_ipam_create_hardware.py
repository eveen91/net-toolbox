from concurrent.futures import ThreadPoolExecutor
import pytest
import auth
import auth_db
import db
from inventory_ipam import repository
from inventory_ipam.router import HardwareCreateRequest
from tests.test_inventory_ipam import subnet
from tests.test_dc_inventory import dc,rack
from tests.test_device_visualization import appliance,BASE


def source(client,status='free',locked=False):
    network=subnet(client)
    db.add_address(network['id'],'10.20.3.7',status,hostname='New firewall',description='Keep original notes',locked=locked)
    with repository.devices.connection() as conn:
        return db._address_dict(conn.execute('SELECT * FROM ipam_addresses').fetchone())


def payload(address,**changes):
    return {'expectedUpdatedAt':address['updatedAt'],'ipPort':'management','device':{**appliance(),'name':'New firewall','managementPort':True,'heightU':1},**changes}


def create(client,address,body=None,headers=None):
    return client.post(f"/api/ipam/addresses/{address['id']}/hardware",json=body or payload(address),headers=headers)


@pytest.mark.parametrize('target',['management','data'])
def test_create_device_ip_and_rack_atomically(client,target):
    address=source(client);cabinet=rack(client,dc(client))
    body=payload(address,ipPort=target);body['device'].update(rackId=cabinet['id'],rackPosition=12)
    response=create(client,address,body)
    assert response.status_code==201,response.text
    hardware=response.json()
    ports=[p for p in hardware['ports'] if p['ipAddress']]
    assert len(ports)==1 and ports[0]['ipAddress']==address['address'] and ports[0]['isManagement']==(target=='management')
    assert hardware['rackId']==cabinet['id'] and hardware['rackPosition']==12
    links=client.get('/api/ipam/inventory-links',params={'address':address['address']}).json()
    assert links['total']==1 and links['items'][0]['id']==hardware['id']
    with repository.devices.connection() as conn:
        row=conn.execute('SELECT * FROM ipam_addresses WHERE id=?',(address['id'],)).fetchone()
        assert row['status']=='used' and row['hostname']=='New firewall' and row['description']=='Keep original notes'
        assert conn.execute("SELECT COUNT(*) FROM dv_audit WHERE device_id=? AND action='ipam_place'",(hardware['id'],)).fetchone()[0]==1
    fresh={**address,'updatedAt':row['updated_at']}
    assert create(client,fresh,payload(fresh,device={**body['device'],'name':'Duplicate'})).status_code==409
    assert client.get(BASE).json()['total']==1


def test_stale_locked_missing_port_and_rack_conflicts_leave_no_hardware(client):
    address=source(client)
    assert create(client,address,payload(address,expectedUpdatedAt='outdated')).status_code==409
    body=payload(address);body['device']['managementPort']=False
    assert create(client,address,body).status_code==400
    body=payload(address);body['device'].update(rackId=999,rackPosition=1)
    assert create(client,address,body).status_code==404
    assert client.get(BASE).json()['total']==0
    with repository.devices.connection(write=True) as conn:
        conn.execute('UPDATE ipam_addresses SET locked=1 WHERE id=?',(address['id'],))
    assert create(client,address).status_code==400
    assert client.get(BASE).json()['total']==0


def test_audit_failure_rolls_back_hardware_and_ipam(client,monkeypatch):
    address=source(client)
    def fail(*args,**kwargs):raise RuntimeError('Audit failed')
    monkeypatch.setattr(db,'_log_address_change',fail)
    with pytest.raises(RuntimeError):create(client,address)
    assert client.get(BASE).json()['total']==0
    with repository.devices.connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM dv_ports').fetchone()[0]==0
        assert conn.execute('SELECT COUNT(*) FROM dv_audit').fetchone()[0]==0
        assert db._address_dict(conn.execute('SELECT * FROM ipam_addresses').fetchone())==address


def test_concurrent_creation_claims_ip_once(client):
    address=source(client)
    def attempt(number):
        request=HardwareCreateRequest.model_validate(payload(address,device={**appliance(),'name':f'Hardware {number}','managementPort':True}))
        try:
            repository.create_from_address(address['id'],request)
            return 'created'
        except repository.devices.Conflict:return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt,range(2)))==['conflict','created']
    assert client.get(BASE).json()['total']==1


def test_create_permissions_and_tenant_scope(client):
    address=source(client)
    for name,permissions in [('no-device',['ipam.read','ipam.write']),('read-only',['ipam.read','device-visualization'])]:
        auth_db.create_role(name,permissions)
        auth_db.create_user(name,auth.hash_password('Password123'),role=name)
        client.post('/api/auth/login',json={'username':name,'password':'Password123'})
        assert create(client,address).status_code==403
        client.post('/api/auth/logout')
    auth_db.create_user('creator-admin',auth.hash_password('Password123'),role='admin')
    client.post('/api/auth/login',json={'username':'creator-admin','password':'Password123'})
    tenant=client.post('/api/tenants',json={'name':'Other hardware'}).json()['id']
    assert create(client,address,headers={'X-Tenant-ID':tenant}).status_code==404
    assert client.get(BASE).json()['total']==0
