"""Reuse IPAM validation and audit inside a version-checked transaction."""
import ipaddress
import json

import db
from device_visualization import repository as devices
from dc_inventory import repository as inventory


def place_port(device_id, port_id, expected_version, actor=None):
    with devices.connection(write=True) as conn:
        device=devices.detail(conn,device_id)
        devices.check_version(device,expected_version)
        port=next((port for port in device['ports'] if port['id']==port_id),None)
        if port is None:
            raise devices.Missing()
        if not port['ipAddress']:
            return {'status':'no_address','message':'No IP address is recorded on this port.'}
        ip=ipaddress.ip_interface(port['ipAddress']).ip
        base={'ip':str(ip),'deviceName':device['name'],'portName':port['name']}
        if ip.version!=4:
            return {**base,'status':'unsupported','message':'Hardware was not placed in IPAM. IPAM currently supports IPv4 only.'}
        matches=[(ipaddress.ip_network(row['cidr']),dict(row)) for row in conn.execute('SELECT id,cidr FROM ipam_subnets') if ip in ipaddress.ip_network(row['cidr'])]
        if not matches:
            return {**base,'status':'no_subnet','message':'Hardware was not placed in IPAM: no subnet contains this IP address in the current tenant.'}
        _,subnet=max(matches,key=lambda match:match[0].prefixlen)
        existing=conn.execute('''SELECT a.*,s.cidr FROM ipam_addresses a JOIN ipam_subnets s ON s.id=a.subnet_id
            WHERE a.address=? ORDER BY CASE WHEN a.subnet_id=? THEN 0 ELSE 1 END,a.id LIMIT 1''',(str(ip),subnet['id'])).fetchone()
        if existing and (existing['status']!='free' or existing['locked']):
            return {**base,'status':'existing' if existing['status']=='used' else 'conflict',
                'subnetId':existing['subnet_id'],'cidr':existing['cidr'],'addressId':existing['id'],
                'message':'An existing IPAM record was preserved; the hardware link uses its documented interface IP.' if existing['status']=='used' else f"Hardware was not placed in IPAM: the existing address is {existing['status']}{' and locked' if existing['locked'] else ''}. Its configuration was preserved."}
        try:
            db.validate_address_in_subnet(str(ip),subnet['cidr'])
            # A child subnet must not bypass a pool or reservation in a parent.
            for _,containing in matches:
                db.validate_address_not_in_dhcp_pool(conn,str(ip),containing['id'])
                db.validate_address_not_in_active_range_reservation(conn,str(ip),containing['id'])
        except ValueError as exc:
            return {**base,'status':'conflict','subnetId':subnet['id'],'cidr':subnet['cidr'],
                'message':f'Hardware was not placed in IPAM: {exc}'}
        description=f"Device Visualization · {device['name']} / {port['name']}"
        if existing:
            old=db._address_dict(existing)
            conn.execute("UPDATE ipam_addresses SET status='used',hostname=COALESCE(hostname,?),description=COALESCE(description,?),machine_type=COALESCE(machine_type,'physical'),updated_at=? WHERE id=?", (device['name'],description,db._now(),existing['id']))
            updated=db._address_dict(conn.execute('SELECT * FROM ipam_addresses WHERE id=?',(existing['id'],)).fetchone())
            db._log_address_change(conn,existing['id'],actor,'update',json.dumps(old),json.dumps(updated),'Free address assigned to documented hardware',str(ip),existing['cidr'])
            devices.audit(conn,device_id,actor,'ipam_place',None,{**updated,'subnetId':existing['subnet_id'],'portId':port_id})
            return {**base,'status':'existing','subnetId':existing['subnet_id'],'cidr':existing['cidr'],'addressId':existing['id'],'message':'The free IPAM address was marked used; existing metadata was preserved.'}

        cursor=conn.execute('''INSERT INTO ipam_addresses(subnet_id,address,status,allocation_type,hostname,description,machine_type,updated_at)
            VALUES(?,?,'used','static',?,?,'physical',?)''',(subnet['id'],str(ip),device['name'],description,db._now()))
        address_id=cursor.lastrowid
        state={'address':str(ip),'status':'used','allocationType':'static','hostname':device['name'],'description':description,'machineType':'physical','deviceId':device_id,'portId':port_id}
        db._log_address_change(conn,address_id,actor,'create',None,json.dumps(state),'Hardware address added from Device Visualization',str(ip),subnet['cidr'])
        devices.audit(conn,device_id,actor,'ipam_place',None,{**state,'subnetId':subnet['id'],'addressId':address_id})
        return {**base,'status':'created','subnetId':subnet['id'],'cidr':subnet['cidr'],'addressId':address_id,'message':f"Hardware placed in {subnet['cidr']}."}


def hardware_for_ip(address, limit=25, offset=0):
    ip=str(ipaddress.IPv4Address(address))
    with devices.connection() as conn:
        where=" WHERE p.ip_address=? OR p.ip_address LIKE ?"
        args=(ip,ip+'/%')
        total=conn.execute('SELECT COUNT(*) FROM dv_ports p'+where,args).fetchone()[0]
        sql=inventory.DEVICE_SQL+' JOIN dv_ports p ON p.device_id=d.id'
        # Keep the current device location; never cache rack labels in IPAM.
        rows=conn.execute(sql.replace('SELECT d.id,','SELECT p.id AS portId,p.ip_address AS ipAddress,d.id,',1)+where+' ORDER BY d.name COLLATE NOCASE,d.id,p.id LIMIT ? OFFSET ?',(*args,limit,offset))
        items=[]
        cache={}
        for row in rows:
            item=dict(row)
            if item['id'] not in cache:
                cache[item['id']]=devices.detail(conn,item['id'])
            item['portName']=next(port['name'] for port in cache[item['id']]['ports'] if port['id']==item['portId'])
            items.append(item)
        return {'items':items,'total':total,'limit':limit,'offset':offset}


def create_from_address(address_id,request,actor=None):
    from device_visualization.schemas import PortAssignment
    with devices.connection(write=True) as conn:
        source=conn.execute('SELECT a.*,s.cidr FROM ipam_addresses a JOIN ipam_subnets s ON s.id=a.subnet_id WHERE a.id=?',(address_id,)).fetchone()
        if source is None:
            raise devices.Missing()
        if source['updated_at']!=request.expectedUpdatedAt:
            raise devices.Conflict({'code':'stale_address','message':'The IPAM address changed. Reload its details before creating hardware.'})
        if source['locked']:
            raise devices.Invalid('Unlock this IPAM address before assigning new hardware')
        if conn.execute('SELECT 1 FROM dv_ports WHERE ip_address=? OR ip_address LIKE ? LIMIT 1',(source['address'],source['address']+'/%')).fetchone():
            raise devices.Conflict({'code':'hardware_exists','message':'This IP is already documented on an existing device. Reload its hardware links instead of creating a duplicate.'})
        try:
            db.validate_address_in_subnet(source['address'],source['cidr'])
            ip=ipaddress.IPv4Address(source['address'])
            for row in conn.execute('SELECT id,cidr FROM ipam_subnets'):
                if ip in ipaddress.ip_network(row['cidr']):
                    db.validate_address_not_in_dhcp_pool(conn,str(ip),row['id'])
                    db.validate_address_not_in_active_range_reservation(conn,str(ip),row['id'])
        except ValueError as exc:
            raise devices.Invalid(str(exc)) from exc
        if request.device.deviceType in ('storage-shelf','cable-management'):
            raise devices.Invalid('Choose a device type with an IP-capable network port')
        if request.ipPort=='management' and not request.device.managementPort:
            raise devices.Invalid('Enable a management port or choose the first data port')
        device=devices.create_device_in_transaction(conn,request.device,actor)
        port=next((port for port in device['ports'] if port['family']!='sas' and port['isManagement']==(request.ipPort=='management')),None)
        if port is None:
            raise devices.Invalid('The chosen device configuration has no suitable port for this IP')
        result=devices.write_port_assignment(conn,device,port,PortAssignment(expectedVersion=device['version'],label=None,leadsTo=None,ipAddress=source['address']),actor)
        old=db._address_dict(source)
        conn.execute("UPDATE ipam_addresses SET status='used',hostname=COALESCE(hostname,?),machine_type=COALESCE(machine_type,'physical'),updated_at=? WHERE id=?",(device['name'],db._now(),address_id))
        updated=db._address_dict(conn.execute('SELECT * FROM ipam_addresses WHERE id=?',(address_id,)).fetchone())
        db._log_address_change(conn,address_id,actor,'update',json.dumps(old),json.dumps({**updated,'deviceId':device['id'],'portId':port['id']}),'Hardware created from IPAM',source['address'],source['cidr'])
        devices.audit(conn,device['id'],actor,'ipam_place',None,{'addressId':address_id,'ip':source['address'],'portId':port['id'],'subnetId':source['subnet_id']})
        return result
