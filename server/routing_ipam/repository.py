"""Source snapshot, subnet creation, hierarchy and audit share one transaction."""
import json
import sqlite3
import db
from .service import interface_network, source_description


class Missing(Exception):
    pass


class Conflict(Exception):
    pass


def import_networks(host, expected_updated_at, names=None, user_id=None):
    conn = db.get_connection()
    try:
        conn.execute('BEGIN IMMEDIATE')
        source = conn.execute('SELECT id,updated_at FROM hosts WHERE name=?', (host,)).fetchone()
        if source is None:
            raise Missing('Routing host not found in this tenant')
        if source['updated_at'] != expected_updated_at:
            raise Conflict('Routing interfaces changed; reload the host before importing')
        stored = [dict(name=row['name'],ipAddress=row['ip_address'],description=row['description'])
                  for row in conn.execute('SELECT name,ip_address,description FROM interfaces WHERE host_id=? ORDER BY id', (source['id'],))]
        routes = [dict(network=row['network'],nextHop=row['next_hop'],interface=row['interface'])
                  for row in conn.execute('SELECT network,next_hop,interface FROM routes WHERE host_id=? ORDER BY id', (source['id'],))]
        interfaces = db.merge_interfaces(stored,routes)
        if names is not None:
            selected = set(names)
            if selected - {item['name'] for item in interfaces}:
                raise Missing('Selected interface not found on this host')
            interfaces = [item for item in interfaces if item['name'] in selected]
        if len(interfaces) > 1000:
            raise ValueError('Import at most 1000 interfaces at a time')
        grouped = {}
        skipped = []
        for interface in interfaces:
            try:
                cidr = interface_network(interface)
            except ValueError as exc:
                skipped.append({'interface':interface['name'],'ipAddress':interface['ipAddress'],
                                'reason':'unsupported_address','message':str(exc)})
                continue
            grouped.setdefault(cidr,[]).append(interface)
        created = []
        for cidr, origins in grouped.items():
            existing = conn.execute('SELECT id FROM ipam_subnets WHERE cidr=?', (cidr,)).fetchone()
            if existing:
                for item in origins:
                    skipped.append({'interface':item['name'],'ipAddress':item['ipAddress'],'cidr':cidr,
                                    'subnetId':existing['id'],'reason':'already_exists','message':'Subnet already exists in IPAM; unchanged'})
                continue
            description = source_description(host,origins)
            cursor = conn.execute('INSERT INTO ipam_subnets(cidr,vlan,description,updated_at) VALUES (?,NULL,?,?)', (cidr,description,db._now()))
            subnet_id = cursor.lastrowid
            state = {'cidr':cidr,'vlan':None,'description':description,'sourceHost':host,'sourceInterfaces':origins}
            db._log_subnet_change(conn,subnet_id,user_id,'subnet_create',None,json.dumps(state),
                                  'Subnet imported from Routing Map interfaces',cidr)
            created.append({'subnetId':subnet_id,'cidr':cidr,'interfaces':[item['name'] for item in origins]})
            for item in origins[1:]:
                skipped.append({'interface':item['name'],'ipAddress':item['ipAddress'],'cidr':cidr,
                                'subnetId':subnet_id,'reason':'duplicate_network','message':'Same network as another imported interface'})
        if created:
            db.recompute_subnet_hierarchy(conn,user_id=user_id)
        conn.commit()
        return {'host':host,'created':created,'skipped':skipped,
                'summary':{'created':len(created),'skipped':len(skipped),'interfaces':len(interfaces)}}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
