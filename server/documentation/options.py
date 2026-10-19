from dc_inventory import repository as inventory
from . import repository as repo,sources,access


def listing(kind,query,device_type,limit,offset):
    access.check(['dhcp-generator'] if kind=='dhcp' else sources.minimum(kind))
    with repo.connection() as conn:
        if kind=='dc':sql=inventory.DC_SQL;name='c.name'
        elif kind=='rack':sql=inventory.RACK_SQL;name='r.name'
        elif kind=='device':sql=inventory.DEVICE_SQL;name='d.name'
        elif kind=='subnet':sql='SELECT id,cidr AS name,description FROM ipam_subnets';name='cidr'
        else:
            sql='''SELECT v.id,c.name,v.number,v.profile,v.created_at AS updatedAt FROM dhcp_versions v
                JOIN dhcp_configurations c ON c.id=v.configuration_id''';name='c.name'
        escaped=query.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        where=f" WHERE {name} LIKE ? ESCAPE '\\'";args=['%'+escaped+'%']
        if kind=='device' and device_type:where+=' AND d.device_type=?';args.append(device_type)
        total=conn.execute('SELECT COUNT(*) FROM ('+sql+where+')',args).fetchone()[0]
        rows=[dict(row) for row in conn.execute(sql+where+' ORDER BY '+name+' LIMIT ? OFFSET ?',(*args,limit,offset))]
        def item(row):
            name=row['name']
            if kind=='dhcp':name+=f" · v{row['number']} · {row['profile']}"
            detail=' · '.join(str(row[k]) for k in ('dataCenterName','rackName','deviceType','description') if row.get(k))
            return {'id':row['id'],'name':name,'detail':detail,'subjectName':row.get('dataCenterName') if kind=='rack' else row['name']}
        return {'items':[item(row) for row in rows],'total':total,'limit':limit,'offset':offset}
