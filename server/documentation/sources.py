"""Bounded, same-transaction adapters using the existing module read models."""
import hashlib
import ipaddress
import json
from datetime import datetime,timezone
import db
from device_visualization import repository as devices
from dc_inventory import repository as inventory,connections
from dhcp_generator import repository as dhcp
from . import access
from .templates import TEMPLATES

MAX_DEVICES=150
MAX_ROWS=2000
MAX_TOTAL=12000


def digest(snapshot):
    value={key:val for key,val in snapshot.items() if key not in ('collectedAt','digest')}
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def minimum(kind):
    return ['ipam.read'] if kind=='subnet' else ['device-visualization','dc-inventory'] if kind!='none' else []


def collect(conn,scope,template):
    from .repository import Missing,Invalid
    kind=scope.get('kind','none');identifier=scope.get('id')
    if kind not in TEMPLATES[template]['scopes']:raise Invalid('The selected scope does not match this document type.')
    requirements=minimum(kind);access.check(requirements)
    snapshot={'schemaVersion':2,'collectedAt':datetime.now(timezone.utc).isoformat(),'scope':scope,'requiredPermissions':requirements[:],
              'sources':[],'tables':[],'warnings':['Saved infrastructure records only; no live discovery or link-health assessment.']}
    def table(key,title,chapter,columns,rows):
        if len(rows)>MAX_ROWS or sum(len(t['rows']) for t in snapshot['tables'])+len(rows)>MAX_TOTAL:raise Invalid('This scope is too large. Choose a smaller rack, device or network; no records were truncated.')
        snapshot['tables'].append({'id':key,'title':title,'chapter':chapter,'columns':columns,'rows':rows})
    def provenance(module,type,id,name,version,updated):
        snapshot['sources'].append({'module':module,'type':type,'id':id,'name':name,'version':version,'updatedAt':updated})
    hardware=[];racks=[];networks=[]
    try:
        if kind in ('dc','rack'):
            entity=inventory.one(conn,'datacenter' if kind=='dc' else 'rack',identifier)
            provenance('dc-inventory',kind,identifier,entity['name'],entity['version'],entity['updatedAt'])
            racks=[entity] if kind=='rack' else [dict(row) for row in conn.execute(inventory.RACK_SQL+' WHERE r.data_center_id=? ORDER BY r.id LIMIT ?',(identifier,MAX_DEVICES+1))]
            if len(racks)>MAX_DEVICES:raise Invalid('Too many racks. Use rack-level documents.')
            ids=[row[0] for row in conn.execute('SELECT id FROM dv_devices WHERE '+('rack_id=?' if kind=='rack' else 'rack_id IN (SELECT id FROM dc_racks WHERE data_center_id=?)')+' ORDER BY id LIMIT ?',(identifier,MAX_DEVICES+1))]
            if len(ids)>MAX_DEVICES:raise Invalid('The selected scope contains more than 150 devices. Choose a smaller scope.')
            hardware=[devices.detail(conn,id) for id in ids]
        elif kind=='device':
            item=devices.detail(conn,identifier)
            if template in ('switch','firewall') and item['deviceType']!=template:raise Invalid('Choose a device matching the document type.')
            hardware=[item]
            if item['rackId']:racks=[inventory.one(conn,'rack',item['rackId'])]
        elif kind=='subnet':
            row=conn.execute('SELECT * FROM ipam_subnets WHERE id=?',(identifier,)).fetchone()
            if row is None:raise Missing()
            networks=[dict(row)];network=ipaddress.ip_network(row['cidr'])
            if access.allowed(['device-visualization','dc-inventory']):
                ids=[]
                for port in conn.execute("SELECT device_id,ip_address FROM dv_ports WHERE ip_address IS NOT NULL AND ip_address!=''"):
                    if ipaddress.ip_interface(port['ip_address']).ip in network and port['device_id'] not in ids:ids.append(port['device_id'])
                    if len(ids)>MAX_DEVICES:raise Invalid('The network contains too many devices. Choose a smaller scope.')
                hardware=[devices.detail(conn,id) for id in sorted(ids)]
                snapshot['requiredPermissions']+=['device-visualization','dc-inventory']
            else:snapshot['warnings'].append('Associated hardware is omitted because inventory access is unavailable.')
    except devices.Missing:raise Missing()
    ids=[d['id'] for d in hardware]
    for d in hardware:
        provenance('device-visualization','device',d['id'],d['name'],d['version'],d['updatedAt'])
        if not d['rackId']:snapshot['warnings'].append(f"{d['name']}: rack location is not recorded.")
    if kind=='subnet':racks=[inventory.one(conn,'rack',id) for id in sorted({d['rackId'] for d in hardware if d['rackId']})]
    for rack in racks:provenance('dc-inventory','rack',rack['id'],rack['name'],rack['version'],rack['updatedAt'])
    if kind!='none':
        table('racks','Rack locations','physical',['DC','Rack','Height U','Used U'],[[r['dataCenterName'],r['name'],r['heightU'],r['usedU']] for r in racks])
        table('devices','Equipment','equipment',['Device','Type','Vendor','Model','DC','Rack','Starting U','Height U'],[[d['name'],d['deviceType'],d['vendor'],d['model'],d['dataCenterName'],d['rackName'],d['rackPosition'],d['heightU']] for d in hardware])
        portrows=[[d['name'],p['name'],p['family'],p['effectiveSpeedGbps'],p['transceiver'],p['ipAddress'],p['portMode'],p['accessVlan'],p['trunkVlans'],p['nativeVlan'],p['label'],p['leadsTo']] for d in hardware for p in d['ports']]
        table('ports','Interfaces','logical',['Device','Port','Connector','Gbps','Module','Address','Mode','Access VLAN','Allowed VLANs','Native VLAN','Label','Destination note'],portrows)
        storage=[d for d in hardware if d['deviceType'] in ('storage','storage-shelf')]
        if storage:table('storage','Storage controllers and bays','equipment',['Device','Bays','Occupied bays','Expansion ports'],[[d['name'],d['driveBayCount'],', '.join(map(str,d['occupiedBays'])),d['expansionPortCount']] for d in storage])
    if ids:
        marks=','.join('?' for _ in ids)
        cable_rows=conn.execute(f'''SELECT c.* FROM dc_connections c JOIN dv_ports a ON a.id=c.source_port_id JOIN dv_ports b ON b.id=c.target_port_id
            WHERE a.device_id IN ({marks}) OR b.device_id IN ({marks}) ORDER BY c.id LIMIT ?''',(*ids,*ids,MAX_ROWS+1)).fetchall()
        if len(cable_rows)>MAX_ROWS:raise Invalid('Too many connections. Narrow the scope.')
        cache={d['id']:d for d in hardware};cables=[];links=[]
        for row in cable_rows:
            a=connections.endpoint(conn,row['source_port_id'],cache);b=connections.endpoint(conn,row['target_port_id'],cache)
            if len(cache)>MAX_DEVICES*2:raise Invalid('Too many connected external devices. Narrow the scope.')
            links.append({'id':row['id'],'label':row['label'],'source':a,'target':b})
            cables.append([row['id'],a['name'],a['portName'],a['effectiveFamily'],a['effectiveSpeedGbps'],b['name'],b['portName'],b['effectiveFamily'],b['effectiveSpeedGbps'],row['label'],a['id'] not in ids or b['id'] not in ids])
            provenance('dc-inventory','connection',row['id'],row['label'] or f"Connection {row['id']}",row['version'],None)
        for peer_id,peer in cache.items():
            if peer_id not in ids:provenance('device-visualization','external-device',peer_id,peer['name'],peer['version'],peer['updatedAt'])
        table('connections','Physical connections','connections',['ID','From device','From port','From medium','From Gbps','To device','To port','To medium','To Gbps','Label','Outside scope'],cables)
    # Typed row references avoid guessing identity from names (which may repeat).
    for t in snapshot['tables']:
        if t['id']=='racks':t.update(referenceColumn=1,rowReferences=[{'module':'dc-inventory','type':'rack','id':r['id']} for r in racks])
        elif t['id']=='devices':t.update(referenceColumn=0,rowReferences=[{'module':'device-visualization','type':'device','id':d['id']} for d in hardware])
        elif t['id']=='connections':t.update(referenceColumn=0,rowReferences=[{'module':'dc-inventory','type':'connection','id':r[0]} for r in t['rows']])
    addresses={str(ipaddress.ip_interface(p['ipAddress']).ip) for d in hardware for p in d['ports'] if p['ipAddress']}
    if kind!='none' and access.allowed(['ipam.read']):
        if kind!='subnet':
            candidates=sorted({str(ipaddress.ip_network(f'{ip}/{prefix}',strict=False)) for ip in addresses if ipaddress.ip_address(ip).version==4 for prefix in range(33)})
            networks=[]
            for offset in range(0,len(candidates),500):
                batch=candidates[offset:offset+500];marks=','.join('?' for _ in batch)
                networks.extend(dict(row) for row in conn.execute(f'SELECT * FROM ipam_subnets WHERE cidr IN ({marks})',batch))
                if len(networks)>MAX_ROWS:raise Invalid('Too many related networks. Narrow the scope.')
            networks.sort(key=lambda row:row['id'])
        if len(networks)>MAX_ROWS:raise Invalid('Too many related networks. Narrow the scope.')
        if networks:
            snapshot['requiredPermissions'].append('ipam.read')
            table('subnets','IPAM networks','logical',['CIDR','VLAN','Description','Updated'],[[n['cidr'],n['vlan'],n['description'],n['updated_at']] for n in networks])
            address_rows=[];pools=[]
            for n in networks:
                provenance('ipam','subnet',n['id'],n['cidr'],None,n['updated_at'])
                if kind=='subnet':records=conn.execute('SELECT * FROM ipam_addresses WHERE subnet_id=? ORDER BY id LIMIT ?',(n['id'],MAX_ROWS+1))
                elif addresses:
                    marks=','.join('?' for _ in addresses)
                    records=conn.execute(f'SELECT * FROM ipam_addresses WHERE subnet_id=? AND address IN ({marks}) ORDER BY id LIMIT ?',(n['id'],*sorted(addresses),MAX_ROWS+1))
                else:records=[]
                for r in records:
                    address_rows.append([n['cidr'],r['address'],r['hostname'],r['status'],r['description'],r['updated_at']])
                    if len(address_rows)>MAX_ROWS:raise Invalid('Too many address records. Narrow the scope.')
                    provenance('ipam','address',r['id'],r['address'],None,r['updated_at'])
                for r in conn.execute('SELECT * FROM ipam_dhcp_pools WHERE subnet_id=? ORDER BY id LIMIT ?',(n['id'],MAX_ROWS+1)):
                    pools.append([n['cidr'],r['start_ip'],r['end_ip'],r['name']])
                    if len(pools)>MAX_ROWS:raise Invalid('Too many DHCP pools. Narrow the scope.')
                    provenance('ipam','pool',r['id'],r['name'] or str(r['id']),None,r['updated_at'])
            table('ipam-addresses','IPAM addresses','logical',['Network','Address','Hostname','Status','Description','Updated'],address_rows)
            table('ipam-pools','IPAM DHCP pools','services',['Network','First address','Last address','Name'],pools)
    elif kind!='none':snapshot['warnings'].append('Related IPAM data is omitted because IPAM Read access is unavailable.')
    if hardware and access.allowed(['routing-map']):
        names={d['name'].strip().lower() for d in hardware}|{ip.lower() for ip in addresses}
        marks=','.join('?' for _ in names)
        hosts=conn.execute(f'SELECT id,name FROM hosts WHERE lower(name) IN ({marks}) ORDER BY id',tuple(sorted(names))).fetchall()
        for row in hosts:
            size=conn.execute('SELECT (SELECT COUNT(*) FROM routes WHERE host_id=?)+(SELECT COUNT(*) FROM interfaces WHERE host_id=?)',(row['id'],row['id'])).fetchone()[0]
            if size>MAX_ROWS:raise Invalid('Routing host exceeds 2,000 saved rows. Use a smaller routing snapshot.')
            host=db.get_host_in_connection(conn,row['name'])
            provenance('routing-map','host',row['id'],host['host'],None,host['updatedAt'])
            table(f'routes-{row["id"]}',f'Routing Map: {host["host"]} routes','logical',['Network','Next hop','Interface'],[[r['network'],r['nextHop'],r['interface']] for r in host['routes']])
            table(f'interfaces-{row["id"]}',f'Routing Map: {host["host"]} interfaces','logical',['Interface','Address / connected network','Description'],[[p['name'],p['ipAddress'],p['description']] for p in host['interfaces']])
            snapshot['requiredPermissions'].append('routing-map')
        if not hosts:snapshot['warnings'].append('No Routing Map host exactly matches the included device names or interface IPs; routing was not guessed.')
        else:snapshot['warnings'].append('Routing Map connected-route fallbacks may contain network addresses rather than interface host addresses.')
    elif hardware:snapshot['warnings'].append('Routing Map data is omitted because module access is unavailable.')
    for version_id in scope.get('dhcpVersionIds',[]):
        access.check(['dhcp-generator']);snapshot['requiredPermissions'].append('dhcp-generator')
        row=conn.execute('SELECT configuration_id FROM dhcp_versions WHERE id=?',(version_id,)).fetchone()
        if row is None:raise Missing()
        item=dhcp.version(conn,row['configuration_id'],version_id,True);config=item['configuration']
        provenance('dhcp-generator','version',version_id,config['firewall'],item['number'],item['createdAt'])
        table('dhcp-'+version_id,'DHCP Generator: '+config['firewall']+' v'+str(item['number']),'services',['Network','Gateway','Pools','Reservations','Active','Interface addresses','Hostname fallback','DNS override','Domain override','Default lease override','Maximum lease override'],[[s['cidr'],s.get('gateway'),'; '.join(p['start']+'–'+p['end'] for p in s.get('pools',[])),len(s.get('reservations',[])),s.get('active',True),s.get('interface_address'),s.get('gaia_host_name_fallback',False),s.get('dns'),s.get('domain'),s.get('default_lease_time'),s.get('max_lease_time')] for s in config.get('subnets',[])])
        table('dhcp-options-'+version_id,'DHCP server options','services',['Firewall','Profile','DNS','Domain','Default lease','Maximum lease'],[[config['firewall'],config['profile'],config.get('dns'),config.get('domain'),config.get('default_lease_time'),config.get('max_lease_time')]])
        reservations=[]
        for subnet in config.get('subnets',[]):
            for reservation in subnet.get('reservations',[]):
                reservations.append([subnet['cidr'],reservation['id'],reservation['ip'],reservation['mac'],reservation.get('active',True)])
                if len(reservations)>MAX_ROWS:raise Invalid('The published DHCP version has more than 2,000 reservations. Attach a smaller configuration version.')
        table('dhcp-reservations-'+version_id,'Published DHCP reservations','services',['Network','Identifier','IP','MAC','Active'],reservations)
    if kind in ('dc','rack'):snapshot['warnings'].append('Unassigned devices have no rack/DC link and are excluded from this location scope; they can be documented individually.')
    if kind=='none' and not scope.get('dhcpVersionIds'):snapshot['warnings'].append('Manual document: no infrastructure records linked.')
    if kind!='none' and not hardware and kind!='subnet':snapshot['warnings'].append('No devices recorded in this scope.')
    for t in snapshot['tables']:
        if t['id']=='subnets':t.update(referenceColumn=0,rowReferences=[{'module':'ipam','type':'subnet','id':n['id']} for n in networks])
    # Freeze only the read-model fields required by local diagram layout. External
    # peers expose endpoints only, never their unrelated ports, notes or neighbors.
    scoped=[{**inventory.device_snapshot(d),'ports':d['ports']} for d in hardware]
    snapshot['diagramData']={'layoutVersion':1,'racks':racks,'devices':scoped,
        'connections':links if ids else [],'networks':[]}
    for n in networks:
        network=ipaddress.ip_network(n['cidr'])
        members=[{'deviceId':d['id'],'name':d['name'],'portId':p['id'],'portName':p['name'],'address':p['ipAddress']}
                 for d in hardware for p in d['ports'] if p['ipAddress'] and ipaddress.ip_interface(p['ipAddress']).ip in network]
        snapshot['diagramData']['networks'].append({'id':n['id'],'cidr':n['cidr'],'vlan':n['vlan'],'members':members})
    snapshot['requiredPermissions']=sorted(set(snapshot['requiredPermissions']))
    snapshot['digest']=digest(snapshot)
    return snapshot
