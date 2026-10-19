import pytest
from device_visualization import repository as repo
from tests.test_device_visualization import create,appliance,config,BASE


def patch(client,d,p,**changes):
    return client.put(f"{BASE}/{d['id']}/ports/{p['id']}",json={'expectedVersion':d['version'],'label':p['label'],'leadsTo':p['leadsTo'],**changes})


@pytest.mark.parametrize('module,family,speed',[('sfp-1g','sfp',1),('sfp-10g','sfp',10),('sfp28-25g','sfp',25),('rj45-1g','ethernet',1)])
def test_individual_sfp_module_roundtrip_preserves_other_ports(client,module,family,speed):
    d=create(client);ports=[p for p in d['ports'] if p['family']=='sfp'];first,second=ports
    response=patch(client,d,first,transceiver=module,ipAddress='192.0.2.1/24',portMode='access',accessVlan=12)
    assert response.status_code==200,response.text
    updated=response.json();p=next(p for p in updated['ports'] if p['id']==first['id'])
    assert (p['family'],p['speedGbps'])==('sfp',10)
    assert (p['transceiver'],p['effectiveFamily'],p['effectiveSpeedGbps'])==(module,family,speed)
    assert next(p for p in updated['ports'] if p['id']==second['id'])==second
    # Legacy writes omit the module and retain it; resetting explicitly uses the group default.
    updated=patch(client,updated,p,label='Changed').json();p=next(p for p in updated['ports'] if p['id']==first['id'])
    assert p['transceiver']==module and p['ipAddress']=='192.0.2.1/24' and p['accessVlan']==12
    current=client.put(f"{BASE}/{d['id']}",json=config(updated)).json()
    assert current==updated
    reset=patch(client,updated,p,transceiver=None).json();p=next(p for p in reset['ports'] if p['id']==first['id'])
    assert p['transceiver'] is None and p['effectiveFamily']=='sfp' and p['effectiveSpeedGbps']==10
    assert p['ipAddress']=='192.0.2.1/24' and p['accessVlan']==12


def test_transceiver_validation_noop_and_removal_protection(client):
    d=create(client);ethernet=d['ports'][0];sfp=next(p for p in d['ports'] if p['family']=='sfp')
    assert patch(client,d,ethernet,transceiver='sfp-1g').status_code==400
    assert patch(client,d,sfp,transceiver='invalid').status_code==422
    d=patch(client,d,sfp,transceiver='rj45-1g').json();p=next(p for p in d['ports'] if p['id']==sfp['id'])
    assert patch(client,d,p,transceiver='rj45-1g').json()==d
    data=config(d);next(g for g in data['portGroups'] if g['family']=='sfp')['count']=0
    preview=client.post(f"{BASE}/{d['id']}/update-preview",json=data).json()
    assert preview['removedConfiguredPortCount']==1
    assert client.put(f"{BASE}/{d['id']}",json=data).status_code==409
    assert client.put(f"{BASE}/{d['id']}",json={**data,'confirmPortDataRemoval':True}).status_code==200


def test_module_migration_preserves_existing_ports_and_audit(client):
    d=create(client)
    history=client.get(f"{BASE}/{d['id']}/audit").json()
    with repo.connection(write=True) as conn:conn.execute('ALTER TABLE dv_ports DROP COLUMN transceiver')
    repo.init_db();repo.init_db()
    assert client.get(f"{BASE}/{d['id']}").json()==d
    assert client.get(f"{BASE}/{d['id']}/audit").json()==history
    with repo.connection() as conn:assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
