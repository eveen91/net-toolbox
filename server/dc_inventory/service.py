"""Inventory mutations share the device transaction, lock and version boundary."""
import sqlite3
from device_visualization import repository as devices
from . import repository as repo


def apply_placement(conn,device_id,request,current=None,validate_only=False):
    fields={'rackId':'rack_id','rackPosition':'rack_position','heightU':'height_u'}
    if current is not None and not fields.keys() & request.model_fields_set:
        return
    values={key:getattr(request,key) if key in request.model_fields_set or current is None else current.get(key) for key in fields}
    kind=current['deviceType'] if current else conn.execute('SELECT device_type FROM dv_devices WHERE id=?',(device_id,)).fetchone()[0]
    if kind=='cable-management' and values['heightU']!=1:
        raise devices.Invalid('Cable management panels occupy exactly 1U')
    if values['rackId'] is None:
        if 'rackPosition' in request.model_fields_set and values['rackPosition'] is not None:
            raise devices.Invalid('Choose a rack before setting the U position')
        values['rackPosition']=None
    else:
        rack=repo.one(conn,'rack',values['rackId'])
        start,height=values['rackPosition'],values['heightU']
        if start is None or height is None:
            raise devices.Invalid('Rack placement requires a starting U and device height in U')
        end=start+height-1
        if end>rack['heightU']:
            raise devices.Invalid(f"Device would end at U{end}, beyond this {rack['heightU']}U rack")
        occupied=conn.execute('''SELECT name,rack_position,height_u FROM dv_devices WHERE rack_id=? AND id!=?
          AND rack_position<=? AND rack_position+height_u-1>=? LIMIT 1''',(rack['id'],device_id,end,start)).fetchone()
        if occupied:
            raise devices.Conflict({'code':'placement_conflict','message':f"U{start}–U{end} overlaps {occupied['name']} (U{occupied['rack_position']}–U{occupied['rack_position']+occupied['height_u']-1})"})
    if validate_only:return
    conn.execute('UPDATE dv_devices SET rack_id=?,rack_position=?,height_u=? WHERE id=?',
                 (values['rackId'],values['rackPosition'],values['heightU'],device_id))


def mutate(kind,request,entity_id=None,actor=None,delete=False):
    table='dc_datacenters' if kind=='datacenter' else 'dc_racks'
    with devices.connection(write=True) as conn:
        old=repo.one(conn,kind,entity_id) if entity_id is not None else None
        if old:
            devices.check_version(old,request.expectedVersion)
        if delete:
            if not request.confirmDelete:
                raise devices.Conflict({'code':'confirmation_required','message':'Confirm deletion of this empty location'})
            if (old['rackCount'] if kind=='datacenter' else old['deviceCount']):
                raise devices.Conflict({'code':'location_not_empty','message':'Remove the racks first' if kind=='datacenter' else 'Move or unassign all devices before deleting this rack'})
            repo.log(conn,kind,entity_id,actor,'delete',old,None)
            conn.execute(f'DELETE FROM {table} WHERE id=?',(entity_id,))
            return {'deleted':True,'id':entity_id}
        dc_id=None
        if kind=='rack':
            dc_id=old['dataCenterId'] if old else request.dataCenterId
            repo.one(conn,'datacenter',dc_id)
            if old:
                highest=conn.execute('SELECT MAX(rack_position+height_u-1) FROM dv_devices WHERE rack_id=?',(entity_id,)).fetchone()[0] or 0
                if highest>request.heightU:
                    raise devices.Conflict({'code':'rack_too_small','message':f'Installed devices reach U{highest}; move them before shrinking the rack'})
        duplicate=conn.execute(f'SELECT id FROM {table} WHERE name=? COLLATE NOCASE AND id!=?'+(' AND data_center_id=?' if kind=='rack' else ''),
            (request.name,entity_id or 0,*((dc_id,) if kind=='rack' else ()))).fetchone()
        if duplicate:
            raise devices.Invalid('This name already exists in the data centre' if kind=='rack' else 'This data centre name already exists')
        if old and old['name']==request.name and old['description']==request.description and (kind=='datacenter' or old['heightU']==request.heightU):
            return old
        stamp=devices.now()
        if old:
            if kind=='datacenter':
                conn.execute('UPDATE dc_datacenters SET name=?,description=?,version=version+1,updated_at=? WHERE id=?',(request.name,request.description,stamp,entity_id))
            else:
                conn.execute('UPDATE dc_racks SET name=?,description=?,height_u=?,version=version+1,updated_at=? WHERE id=?',(request.name,request.description,request.heightU,stamp,entity_id))
        elif kind=='datacenter':
            entity_id=conn.execute('INSERT INTO dc_datacenters(name,description,created_at,updated_at) VALUES(?,?,?,?)',(request.name,request.description,stamp,stamp)).lastrowid
        else:
            entity_id=conn.execute('INSERT INTO dc_racks(data_center_id,name,description,height_u,created_at,updated_at) VALUES(?,?,?,?,?,?)',(dc_id,request.name,request.description,request.heightU,stamp,stamp)).lastrowid
        result=repo.one(conn,kind,entity_id)
        repo.log(conn,kind,entity_id,actor,'update' if old else 'create',old,result)
        return result


def place(device_id,request,actor=None):
    with devices.connection(write=True) as conn:
        current=devices.detail(conn,device_id)
        devices.check_version(current,request.expectedVersion)
        old=repo.one(conn,'device',device_id)
        apply_placement(conn,device_id,request,current)
        candidate=repo.one(conn,'device',device_id)
        if candidate==old:
            return candidate
        conn.execute('UPDATE dv_devices SET version=version+1,updated_at=? WHERE id=?',(devices.now(),device_id))
        result=repo.one(conn,'device',device_id)
        devices.audit(conn,device_id,actor,'device_location_update',current,devices.detail(conn,device_id))
        repo.log(conn,'device',device_id,actor,'placement',old,result)
        return result


def create_cable_panel(request,actor=None):
    from device_visualization.schemas import DeviceCreate
    config=DeviceCreate(deviceType='cable-management',heightU=1,portGroups=[],**request.model_dump())
    result=devices.create_device(config,actor)
    return repo.device_snapshot(result)
