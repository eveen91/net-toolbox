"""Tenant-local drafts, source manifests, review transitions and frozen revisions."""
import difflib
import json
from contextlib import contextmanager
from datetime import datetime,timezone
import db
from . import access,templates,sources
from tenancy.context import current_tenant

class Missing(Exception):pass
class Conflict(Exception):pass
class VersionExists(Exception):pass
class Invalid(Exception):pass
class StateConflict(Exception):pass


def now():return datetime.now(timezone.utc).isoformat()
def dump(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


@contextmanager
def connection(write=False):
    conn=db.get_connection()
    try:
        conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        yield conn
        if write:conn.commit()
    finally:conn.close()


def init_db():
    with connection(True) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS documentation_dc_forms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,dc_name TEXT NOT NULL,payload TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS documentation_dc_form_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,document_id INTEGER NOT NULL,actor_id INTEGER,action TEXT NOT NULL,
            old_payload TEXT,new_payload TEXT NOT NULL,created_at TEXT NOT NULL)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS documentation_dc_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,document_id INTEGER NOT NULL REFERENCES documentation_dc_forms(id),
            number INTEGER NOT NULL,draft_version INTEGER NOT NULL,payload TEXT NOT NULL,description TEXT NOT NULL,
            actor_id INTEGER,actor_name TEXT,created_at TEXT NOT NULL,markdown BLOB NOT NULL,artifact BLOB NOT NULL,sha256 TEXT NOT NULL,
            UNIQUE(document_id,number),UNIQUE(document_id,draft_version))''')
        migrations={'documentation_dc_forms':{
            'status':"TEXT NOT NULL DEFAULT 'draft'",'snapshot':"TEXT NOT NULL DEFAULT '{}'",
            'required_permissions':"TEXT NOT NULL DEFAULT '[]'",'published_version':'INTEGER'},
            'documentation_dc_versions':{'kind':"TEXT NOT NULL DEFAULT 'saved'",'required_permissions':"TEXT NOT NULL DEFAULT '[]'"}}
        for table,columns in migrations.items():
            present={row['name'] for row in conn.execute(f'PRAGMA table_info({table})')}
            for name,definition in columns.items():
                if name not in present:conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
        from .confluence_profiles import init_schema
        init_schema(conn)
        conn.execute('CREATE INDEX IF NOT EXISTS documentation_audit_document ON documentation_dc_form_audit(document_id,id DESC)')
        for operation in ('UPDATE','DELETE'):
            conn.execute(f'''CREATE TRIGGER IF NOT EXISTS documentation_dc_versions_no_{operation.lower()}
                BEFORE {operation} ON documentation_dc_versions BEGIN SELECT RAISE(ABORT,'Documentation versions are immutable'); END''')


def check_snapshot(document):access.check(document.get('snapshot',{}).get('requiredPermissions',[]))


def detail(conn,identifier):
    row=conn.execute('SELECT * FROM documentation_dc_forms WHERE id=?',(identifier,)).fetchone()
    if row is None:raise Missing()
    access.check(json.loads(row['required_permissions']))
    result={'id':row['id'],'tenantId':current_tenant.get().tenant_id if current_tenant.get() else 'default','form':json.loads(row['payload']),'version':row['version'],'status':row['status'],
            'snapshot':json.loads(row['snapshot']),'publishedVersion':row['published_version'],
            'createdAt':row['created_at'],'updatedAt':row['updated_at']}
    result['validation']=templates.completeness(result)
    return result


def get(identifier):
    with connection() as conn:return detail(conn,identifier)


def permission_clause():
    values=access.expanded()
    if '*' in values:return '1=1',[]
    if not values:return 'json_array_length(required_permissions)=0',[]
    ordered=sorted(values);marks=','.join('?' for _ in ordered)
    return f'NOT EXISTS(SELECT 1 FROM json_each(required_permissions) p WHERE p.value NOT IN ({marks}))',ordered


def listing(limit,offset,query='',status=None,template=None):
    with connection() as conn:
        clause,args=permission_clause()
        escaped=query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        clause+=" AND title LIKE ? ESCAPE '\\'";args.append('%'+escaped+'%')
        if status:clause+=' AND status=?';args.append(status)
        if template:clause+=" AND COALESCE(json_extract(payload,'$.templateId'),'network')=?";args.append(template)
        total=conn.execute('SELECT COUNT(*) FROM documentation_dc_forms WHERE '+clause,args).fetchone()[0]
        rows=conn.execute('''SELECT id,title,dc_name AS dcName,version,status,updated_at AS updatedAt,
            COALESCE(json_extract(payload,'$.templateId'),'network') AS templateId
            FROM documentation_dc_forms WHERE '''+clause+' ORDER BY updated_at DESC,id DESC LIMIT ? OFFSET ?',(*args,limit,offset))
        return {'items':[dict(row) for row in rows],'total':total,'limit':limit,'offset':offset}


def log(conn,identifier,actor,action,old,new):
    conn.execute('''INSERT INTO documentation_dc_form_audit
        (document_id,actor_id,action,old_payload,new_payload,created_at) VALUES(?,?,?,?,?,?)''',
        (identifier,actor,action,dump(old) if old is not None else None,dump(new),now()))


def current(conn,identifier,expected):
    item=detail(conn,identifier)
    if item['version']!=expected:raise Conflict()
    return item


def require_draft(item):
    if item['status']!='draft':raise StateConflict('Return to draft before editing or refreshing this document.')


def store(conn,form,snapshot,identifier):
    conn.execute('''UPDATE documentation_dc_forms SET title=?,dc_name=?,payload=?,snapshot=?,required_permissions=?,
        version=version+1,updated_at=? WHERE id=?''',
        (form['title'],form.get('dcName',''),dump(form),dump(snapshot),dump(snapshot.get('requiredPermissions',[])),now(),identifier))


def save(form,actor_id,identifier=None,expected=None):
    access.action('write')
    stamp=now()
    with connection(True) as conn:
        old=None;scope=form.get('scopeSpec',{'kind':'none','id':None})
        if identifier is not None:
            old=current(conn,identifier,expected);require_draft(old)
            if old['form'].get('templateId','network')!=form.get('templateId','network'):raise Invalid('Create a new document to use a different template.')
        snapshot=old['snapshot'] if old and old['form'].get('scopeSpec',{'kind':'none','id':None})==scope else sources.collect(conn,scope,form.get('templateId','network'))
        if old:store(conn,form,snapshot,identifier)
        else:
            identifier=conn.execute('''INSERT INTO documentation_dc_forms
                (title,dc_name,payload,snapshot,required_permissions,created_at,updated_at) VALUES(?,?,?,?,?,?,?)''',
                (form['title'],form.get('dcName',''),dump(form),dump(snapshot),dump(snapshot.get('requiredPermissions',[])),stamp,stamp)).lastrowid
        log(conn,identifier,actor_id,'update' if old else 'create',old['form'] if old else None,form)
        return detail(conn,identifier)


def _freeze(conn,document,description,actor,kind='saved'):
    from .exports import artifacts
    identifier=document['id'];expected=document['version'];stamp=now()
    if conn.execute('SELECT 1 FROM documentation_dc_versions WHERE document_id=? AND draft_version=?',(identifier,expected)).fetchone():raise VersionExists()
    document={**document,'chapters':templates.chapters(document['form']),'sourceChapterMap':templates.TEMPLATES[document['form'].get('templateId','network')].get('sourceChapters',{}),'templateVersion':templates.TEMPLATES[document['form'].get('templateId','network')]['version'],'schemaVersion':3,'rendererVersion':3}
    number=conn.execute('SELECT COALESCE(MAX(number),0)+1 FROM documentation_dc_versions WHERE document_id=?',(identifier,)).fetchone()[0]
    markdown,artifact,digest=artifacts(document,number,stamp,description)
    conn.execute('''INSERT INTO documentation_dc_versions
        (document_id,number,draft_version,payload,description,actor_id,actor_name,created_at,markdown,artifact,sha256,kind,required_permissions)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (identifier,number,expected,dump(document),description,(actor or {}).get('id'),(actor or {}).get('username'),stamp,
         markdown,artifact,digest,kind,dump(document.get('snapshot',{}).get('requiredPermissions',[]))))
    log(conn,identifier,(actor or {}).get('id'),'publish' if kind=='published' else 'create_version',None,
        {'number':number,'draftVersion':expected,'actorName':(actor or {}).get('username'),'description':description})
    return version_detail(conn,identifier,number)


def create_version(identifier,expected,description,actor):
    access.action('write')
    with connection(True) as conn:
        document=current(conn,identifier,expected);require_draft(document)
        return _freeze(conn,document,description,actor)


def versions(identifier,limit,offset):
    with connection() as conn:
        document=detail(conn,identifier);clause,args=permission_clause()
        current_row=conn.execute('SELECT number FROM documentation_dc_versions WHERE document_id=? AND draft_version=? AND '+clause,(identifier,document['version'],*args)).fetchone()
        where=' WHERE document_id=? AND '+clause
        total=conn.execute('SELECT COUNT(*) FROM documentation_dc_versions'+where,(identifier,*args)).fetchone()[0]
        rows=conn.execute('''SELECT number,draft_version AS draftVersion,description,actor_name AS createdBy,
            created_at AS createdAt,sha256,kind FROM documentation_dc_versions'''+where+' ORDER BY number DESC LIMIT ? OFFSET ?',(identifier,*args,limit,offset))
        return {'items':[dict(row) for row in rows],'total':total,'limit':limit,'offset':offset,
                'versionForCurrentDraft':current_row['number'] if current_row else None}


def version_detail(conn,identifier,number):
    row=conn.execute('''SELECT number,draft_version AS draftVersion,description,actor_name AS createdBy,
        created_at AS createdAt,sha256,payload,kind,required_permissions FROM documentation_dc_versions WHERE document_id=? AND number=?''',(identifier,number)).fetchone()
    if row is None:raise Missing()
    access.check(json.loads(row['required_permissions']))
    result=dict(row);result.pop('required_permissions');result['document']=json.loads(result.pop('payload'));check_snapshot(result['document'])
    return result


def get_version(identifier,number):
    with connection() as conn:return version_detail(conn,identifier,number)


def download(identifier,number,format,actor_id):
    with connection(True) as conn:
        version_detail(conn,identifier,number)
        row=conn.execute('SELECT markdown,artifact FROM documentation_dc_versions WHERE document_id=? AND number=?',(identifier,number)).fetchone()
        log(conn,identifier,actor_id,'export',None,{'number':number,'format':format})
        return bytes(row['markdown' if format=='md' else 'artifact'])


def transition(identifier,expected,action,description,actor):
    access.action('publish' if action=='publish' else 'write')
    with connection(True) as conn:
        item=current(conn,identifier,expected);old=item['status'];published=None
        if action=='submit':
            require_draft(item)
            if not item['validation']['ready']:raise Invalid({'message':'Complete the required review fields.','validation':item['validation']})
            target='review'
        elif action=='draft':
            if old=='draft':raise StateConflict('The document is already a draft.')
            target='draft'
        else:
            if old!='review':raise StateConflict('Submit the saved draft for review before publishing.')
            if not item['validation']['ready']:raise Invalid({'message':'Complete the required review fields.','validation':item['validation']})
            target='published'
            item['status']='published';item['publication']={'reviewedBy':(actor or {}).get('username'),'reviewerId':(actor or {}).get('id'),'reviewedAt':now()}
            published=_freeze(conn,item,description,actor,'published')['number']
        conn.execute('''UPDATE documentation_dc_forms SET status=?,version=version+1,updated_at=?,
            published_version=COALESCE(?,published_version) WHERE id=?''',(target,now(),published,identifier))
        log(conn,identifier,(actor or {}).get('id'),'transition',{'status':old},{'status':target,'description':description,'actorName':(actor or {}).get('username')})
        return detail(conn,identifier)


def source_preview(identifier,expected):
    with connection() as conn:
        document=current(conn,identifier,expected)
        snapshot=sources.collect(conn,document['form'].get('scopeSpec',{'kind':'none','id':None}),document['form'].get('templateId','network'))
        old={t['id']:t for t in document['snapshot'].get('tables',[])};new={t['id']:t for t in snapshot.get('tables',[])}
        changes=[{'id':key,'title':(new.get(key) or old[key])['title'],'before':len(old.get(key,{}).get('rows',[])),
                  'after':len(new.get(key,{}).get('rows',[]))} for key in sorted(old.keys()|new.keys()) if old.get(key)!=new.get(key)]
        return {'snapshot':snapshot,'changes':changes}


def refresh(identifier,expected,digest,actor_id):
    access.action('write')
    with connection(True) as conn:
        document=current(conn,identifier,expected);require_draft(document)
        snapshot=sources.collect(conn,document['form'].get('scopeSpec',{'kind':'none','id':None}),document['form'].get('templateId','network'))
        if snapshot['digest']!=digest:raise StateConflict('Infrastructure changed after the preview. Preview the changes again before applying them.')
        store(conn,document['form'],snapshot,identifier)
        log(conn,identifier,actor_id,'refresh',{'collectedAt':document['snapshot'].get('collectedAt')},{'collectedAt':snapshot['collectedAt']})
        return detail(conn,identifier)


def compare(identifier,before,after):
    with connection() as conn:
        a=version_detail(conn,identifier,before)['document'];b=version_detail(conn,identifier,after)['document']
        def comparable(item):return json.dumps({key:item.get(key) for key in ('form','snapshot','status')},indent=2,ensure_ascii=False,sort_keys=True).splitlines()
        lines=list(difflib.unified_diff(comparable(a),comparable(b),fromfile=f'v{before}',tofile=f'v{after}',lineterm=''))
        labels={f['id']:f['label'] for doc in (a,b) for page in (doc.get('chapters') or templates.chapters(doc['form'])) for section in page['sections'] for f in section['fields']}
        changed=sorted(key for key in a['form'].keys()|b['form'].keys() if a['form'].get(key)!=b['form'].get(key))
        field_changes=[]
        for key in changed:
            if key=='templateNotes':
                left=a['form'].get(key,{}) or {};right=b['form'].get(key,{}) or {}
                field_changes.extend({'label':labels.get(note,note),'before':left.get(note,''),'after':right.get(note,'')} for note in sorted(left.keys()|right.keys()) if left.get(note)!=right.get(note))
            else:field_changes.append({'label':labels.get(key,{'scopeSpec':'Included infrastructure','templateId':'Document type'}.get(key,key)),'before':a['form'].get(key,''),'after':b['form'].get(key,'')})
        old={t['id']:t for t in a.get('snapshot',{}).get('tables',[])};new={t['id']:t for t in b.get('snapshot',{}).get('tables',[])}
        table_changes=[{'title':(new.get(key) or old[key])['title'],'before':len(old.get(key,{}).get('rows',[])),'after':len(new.get(key,{}).get('rows',[]))} for key in sorted(old.keys()|new.keys()) if old.get(key)!=new.get(key)]
        return {'before':before,'after':after,'diff':'\n'.join(lines[:3000]),'truncated':len(lines)>3000,'changedFields':changed,
                'fieldChanges':field_changes,'tableChanges':table_changes}


def restore(identifier,number,expected,actor_id):
    access.action('write')
    with connection(True) as conn:
        item=current(conn,identifier,expected);require_draft(item)
        old=version_detail(conn,identifier,number)['document']
        store(conn,old['form'],old.get('snapshot',{}),identifier)
        log(conn,identifier,actor_id,'restore',None,{'number':number})
        return detail(conn,identifier)


def history(identifier,limit,offset):
    with connection() as conn:
        detail(conn,identifier)
        total=conn.execute('SELECT COUNT(*) FROM documentation_dc_form_audit WHERE document_id=?',(identifier,)).fetchone()[0]
        rows=conn.execute('''SELECT id,actor_id AS actorId,action,created_at AS createdAt,
            CASE WHEN action IN ('transition','publish','create_version') THEN json_extract(new_payload,'$.actorName') END AS actorName,
            CASE WHEN action='transition' THEN json_extract(new_payload,'$.status') END AS targetStatus FROM documentation_dc_form_audit
            WHERE document_id=? ORDER BY id DESC LIMIT ? OFFSET ?''',(identifier,limit,offset))
        return {'items':[dict(row) for row in rows],'total':total,'limit':limit,'offset':offset}


def asset(identifier,number,filename,actor_id):
    """Serve only the immutable revision's declared assets with source checks."""
    import io
    import zipfile
    with connection(True) as conn:
        version=version_detail(conn,identifier,number)
        permitted={path for item in version['document'].get('assets',[]) for path in item['files'].values()}
        path='assets/'+filename
        if path not in permitted:raise Missing()
        row=conn.execute('SELECT artifact FROM documentation_dc_versions WHERE document_id=? AND number=?',(identifier,number)).fetchone()
        with zipfile.ZipFile(io.BytesIO(row['artifact'])) as archive:content=archive.read(path)
        log(conn,identifier,actor_id,'export',None,{'number':number,'format':'asset','filename':filename})
        return content
