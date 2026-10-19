"""Durable publication journal, optimistic local claims and tenant/source access."""
import json
import time
import uuid
from . import access,repository as docs,confluence_profiles as profiles

LEASE_SECONDS=180
TERMINAL={'succeeded','abandoned'}
DONE={'succeeded','skipped','kept'}


def init_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS documentation_confluence_jobs (
        id TEXT PRIMARY KEY,preview_id TEXT NOT NULL UNIQUE REFERENCES documentation_confluence_previews(id),
        profile_id INTEGER NOT NULL,document_id INTEGER NOT NULL,version_number INTEGER NOT NULL,
        status TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1,active INTEGER NOT NULL DEFAULT 1,
        required_permissions TEXT NOT NULL,payload TEXT NOT NULL,actor_id INTEGER,
        lease_owner TEXT,lease_until REAL NOT NULL DEFAULT 0,retry_at REAL NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,updated_at TEXT NOT NULL)''')
    conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS documentation_confluence_job_active ON documentation_confluence_jobs(profile_id,document_id) WHERE active=1')
    conn.execute('''CREATE TABLE IF NOT EXISTS documentation_confluence_steps (
        job_id TEXT NOT NULL REFERENCES documentation_confluence_jobs(id),ordinal INTEGER NOT NULL,
        kind TEXT NOT NULL,page_key TEXT,filename TEXT,operation_id TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'pending',sent INTEGER NOT NULL DEFAULT 0,attempts INTEGER NOT NULL DEFAULT 0,
        result TEXT NOT NULL DEFAULT '{}',error_code TEXT,error_message TEXT,updated_at TEXT NOT NULL,
        PRIMARY KEY(job_id,ordinal))''')
    existing={r['name'] for r in conn.execute('PRAGMA table_info(documentation_confluence_pages)')}
    if 'preserve_remote' not in existing:conn.execute('ALTER TABLE documentation_confluence_pages ADD COLUMN preserve_remote INTEGER NOT NULL DEFAULT 0')


def row(conn,job_id,identifier,number):
    access.action('publish')
    docs.version_detail(conn,identifier,number)
    result=conn.execute('SELECT * FROM documentation_confluence_jobs WHERE id=? AND document_id=? AND version_number=?',(job_id,identifier,number)).fetchone()
    if result is None:raise docs.Missing()
    access.check(json.loads(result['required_permissions']))
    return dict(result)


def detail(conn,job_id,identifier,number,limit=50,offset=0):
    result=row(conn,job_id,identifier,number);payload=json.loads(result.pop('payload'))
    result.pop('required_permissions');result.pop('lease_owner')
    result.update(profileName=payload['profileName'],baseUrl=payload['baseUrl'],spaceKey=payload['spaceKey'],parentPageId=payload['parentPageId'],
                  previewId=result.pop('preview_id'),documentId=result.pop('document_id'),version=result.pop('version_number'),
                  profileId=result.pop('profile_id'),createdAt=result.pop('created_at'),updatedAt=result.pop('updated_at'),
                  leaseUntil=result.pop('lease_until'),retryAt=result.pop('retry_at'))
    counts={r['status']:r['total'] for r in conn.execute('SELECT status,COUNT(*) total FROM documentation_confluence_steps WHERE job_id=? GROUP BY status',(job_id,))}
    steps=[]
    for step in conn.execute('SELECT * FROM documentation_confluence_steps WHERE job_id=? ORDER BY ordinal LIMIT ? OFFSET ?',(job_id,limit,offset)):
        item=dict(step);item.pop('job_id');item['result']=json.loads(item['result'])
        page=next((p for p in payload['pages'] if p['key']==item['page_key']),None)
        item['title']=page['title'] if page else 'Final audience verification'
        if item['result'].get('id'):item['destinationUrl']=payload['baseUrl']+'/pages/viewpage.action?pageId='+str(item['result'].get('pageId') or item['result']['id'])
        steps.append(item)
    total=sum(counts.values())
    result['partial']=bool(sum(counts.get(s,0) for s in DONE) and result['status'] not in TERMINAL)
    result.update(counts=counts,total=total,completed=sum(counts.get(s,0) for s in DONE),steps={'items':steps,'total':total,'limit':limit,'offset':offset},
                  inFlight=result['leaseUntil']>time.time())
    return result


def get(job_id,identifier,number,limit=50,offset=0):
    with docs.connection() as conn:return detail(conn,job_id,identifier,number,limit,offset)


def listing(identifier,number,limit,offset):
    access.action('publish')
    with docs.connection() as conn:
        docs.version_detail(conn,identifier,number)
        clause,args=docs.permission_clause();where='document_id=? AND version_number=? AND ('+clause+')'
        total=conn.execute('SELECT COUNT(*) FROM documentation_confluence_jobs WHERE '+where,(identifier,number,*args)).fetchone()[0]
        rows=conn.execute('SELECT id,status,revision,profile_id AS profileId,created_at AS createdAt,updated_at AS updatedAt FROM documentation_confluence_jobs WHERE '+where+' ORDER BY created_at DESC LIMIT ? OFFSET ?',(identifier,number,*args,limit,offset))
        return {'items':[dict(r) for r in rows],'total':total,'limit':limit,'offset':offset}


def control(job_id,identifier,number,expected,action,actor):
    with docs.connection(True) as conn:
        job=row(conn,job_id,identifier,number)
        if job['revision']!=expected:raise docs.Conflict()
        if job['lease_until']>time.time():raise docs.StateConflict('An operation is still in flight. Wait before changing this publication.')
        if job['status'] in TERMINAL:raise docs.StateConflict('This publication is already finished.')
        unresolved=conn.execute("SELECT 1 FROM documentation_confluence_steps WHERE job_id=? AND (sent=1 AND status NOT IN ('succeeded','skipped','kept','failed','conflict'))",(job_id,)).fetchone()
        if action=='abandon' and unresolved:raise docs.StateConflict('An uncertain write must be reconciled before abandoning this publication.')
        status='abandoned' if action=='abandon' else 'paused'
        conn.execute('UPDATE documentation_confluence_jobs SET status=?,active=?,revision=revision+1,updated_at=? WHERE id=?',(status,int(action!='abandon'),docs.now(),job_id))
        profiles.audit(conn,job['profile_id'],actor,action+'_publication',{'jobId':job_id},identifier)
        return detail(conn,job_id,identifier,number)
