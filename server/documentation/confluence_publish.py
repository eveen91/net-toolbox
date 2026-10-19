"""Execute one bounded, journaled publication step per authorized request."""
import io
import json
import sqlite3
import time
import uuid
import zipfile
from xml.etree import ElementTree as ET
from . import access,repository as docs,confluence_profiles as profiles,confluence_preview as previews,confluence_jobs as jobs
from .confluence_publish_client import PublishingClient,WriteError,numeric
from .confluence_client import RemoteError
from .confluence_render import sha
from .confluence_audience import capture


class PublicationConflict(Exception):pass
class Uncertain(Exception):pass


def marker(value):return f'<ac:structured-macro ac:name="anchor"><ac:parameter ac:name="">{value}</ac:parameter></ac:structured-macro>'


def has_marker(storage,value):
    try:
        root=ET.fromstring('<root xmlns:ac="urn:ac" xmlns:ri="urn:ri">'+storage+'</root>')
        return any(n.attrib.get('{urn:ac}name')=='anchor' and any(p.text==value for p in n) for n in root.iter('{urn:ac}structured-macro'))
    except (ET.ParseError,TypeError):return False


def start(identifier,number,request,actor):
    access.action('publish')
    plan=previews.get(request.previewId,identifier,number)
    if plan['profileVersion']!=request.expectedVersion or plan['profileChanged']:raise docs.Conflict()
    if not plan.get('audienceHash'):raise docs.Invalid('Prepare a new preview with destination audience details before publication.')
    keep=set(request.keepRemoteKeys);replace=set(request.replaceReviewedKeys);by_key={p['key']:p for p in plan['pages']}
    if len(keep)!=len(request.keepRemoteKeys) or len(replace)!=len(request.replaceReviewedKeys) or keep&replace or (keep|replace)-by_key.keys():raise docs.Invalid('Choose unique, distinct reviewed page decisions.')
    for key in keep|replace:
        page=by_key[key]
        if not page.get('remoteId') or not page.get('remoteHash'):raise docs.Invalid('Only an existing mapped page with readable content can be kept or explicitly replaced.')
        if key in replace and any(a['action']=='conflict' for a in page['attachments']):raise docs.Invalid('Attachment conflicts cannot be overwritten. Keep the remote page or resolve the attachment separately.')
    for page in plan['pages']:
        if page['action']=='conflict' and page['key'] not in keep|replace:
            # A parent conflict may be resolved explicitly without replacing a child.
            own=[issue for issue in page['issues'] if not issue.startswith('A parent page has a conflict')]
            if own:raise docs.Invalid('Resolve each conflicted page with Keep remote or Replace reviewed content before publishing.')
    plan['decisions']={'keep':sorted(keep|({p['key'] for p in plan['pages'] if p.get('planAction',p['action'])=='keep'}-replace)),'replace':sorted(replace)}
    stamp=docs.now();job_id=str(uuid.uuid4())
    try:
        with docs.connection(True) as conn:
            docs.version_detail(conn,identifier,number);access.check(plan['requiredPermissions'])
            profile=profiles.row(conn,plan['profileId'])
            if profile['version']!=request.expectedVersion or not json.loads(profile['settings'])['enabled']:raise docs.Conflict()
            existing=conn.execute('SELECT id,payload FROM documentation_confluence_jobs WHERE preview_id=?',(request.previewId,)).fetchone()
            if existing:
                if json.loads(existing['payload'])['decisions']!=plan['decisions']:raise docs.StateConflict('This preview already has a publication with different decisions.')
                return jobs.detail(conn,existing['id'],identifier,number)
            if conn.execute('SELECT 1 FROM documentation_confluence_jobs WHERE profile_id=? AND document_id=? AND active=1',(plan['profileId'],identifier)).fetchone():raise docs.StateConflict('A publication already reserves this destination. Resume or abandon that job first.')
            conn.execute('''INSERT INTO documentation_confluence_jobs(id,preview_id,profile_id,document_id,version_number,status,required_permissions,payload,actor_id,created_at,updated_at)
                VALUES(?,?,?,?,?,'pending',?,?,?,?,?)''',(job_id,request.previewId,plan['profileId'],identifier,number,docs.dump(plan['requiredPermissions']),docs.dump(plan),actor,stamp,stamp))
            steps=[('page',p['key'],None) for p in plan['pages']]
            steps += [('asset',p['key'],a['filename']) for p in plan['pages'] for a in p['attachments']]
            steps += [('verify',p['key'],None) for p in plan['pages']]+[('audience',None,None)]
            for ordinal,(kind,key,filename) in enumerate(steps):
                conn.execute('INSERT INTO documentation_confluence_steps(job_id,ordinal,kind,page_key,filename,operation_id,updated_at) VALUES(?,?,?,?,?,?,?)',(job_id,ordinal,kind,key,filename,str(uuid.uuid4()),stamp))
            profiles.audit(conn,plan['profileId'],actor,'start_publication',{'jobId':job_id,'previewId':request.previewId,'audienceConfirmed':True,'decisions':plan['decisions']},identifier)
            return jobs.detail(conn,job_id,identifier,number)
    except sqlite3.IntegrityError as exc:
        if 'documentation_confluence_jobs' in str(exc):raise docs.StateConflict('Another publication already claimed this preview or destination.') from exc
        raise


def step_map(conn,job_id):return {r['page_key']:json.loads(r['result']) for r in conn.execute("SELECT page_key,result FROM documentation_confluence_steps WHERE job_id=? AND kind='page' AND status IN ('succeeded','skipped','kept')",(job_id,))}


def claim(job_id,identifier,number,expected,actor):
    owner=str(uuid.uuid4())
    with docs.connection(True) as conn:
        job=jobs.row(conn,job_id,identifier,number)
        if job['revision']!=expected:raise docs.Conflict()
        if job['status'] in jobs.TERMINAL:return job,None,None,None
        if job['status']=='conflict':raise docs.StateConflict('This publication has a conflict. Keep the remote changes and prepare a fresh preview after abandoning this job.')
        if job['lease_until']>time.time():raise docs.StateConflict('Another request is processing this publication. Reload after it finishes.')
        if job['retry_at']>time.time():raise docs.StateConflict('Confluence requested a retry delay. Wait before resuming.')
        plan=json.loads(job['payload']);profiles.load(job['profile_id'],plan['profileVersion'])
        row=conn.execute("SELECT * FROM documentation_confluence_steps WHERE job_id=? AND status NOT IN ('succeeded','skipped','kept') ORDER BY ordinal LIMIT 1",(job_id,)).fetchone()
        if row is None:raise docs.StateConflict('Publication journal is incomplete.')
        step=dict(row);step['result']=json.loads(step['result'])
        if step['status'] in ('inflight','uncertain') and step['sent']:step['recover']=True
        else:step['recover']=False
        conn.execute("UPDATE documentation_confluence_jobs SET status='running',lease_owner=?,lease_until=?,revision=revision+1,updated_at=? WHERE id=?",(owner,time.time()+jobs.LEASE_SECONDS,docs.now(),job_id))
        parents=step_map(conn,job_id)
        profiles.audit(conn,job['profile_id'],actor,'advance_publication',{'jobId':job_id,'step':step['ordinal'],'reconcile':step['recover']},identifier)
    return job,step,owner,parents


def sent(job_id,step,owner):
    with docs.connection(True) as conn:
        live=conn.execute('SELECT lease_owner,lease_until FROM documentation_confluence_jobs WHERE id=?',(job_id,)).fetchone()
        if live['lease_owner']!=owner or live['lease_until']<=time.time():raise docs.StateConflict('The publication claim expired before writing.')
        conn.execute("UPDATE documentation_confluence_steps SET status='inflight',sent=1,attempts=attempts+1,error_code=NULL,error_message=NULL,updated_at=? WHERE job_id=? AND ordinal=?",(docs.now(),job_id,step['ordinal']))


def stash(job_id,step,owner,result):
    with docs.connection(True) as conn:
        if conn.execute('SELECT lease_owner FROM documentation_confluence_jobs WHERE id=?',(job_id,)).fetchone()[0]!=owner:raise docs.Conflict()
        conn.execute('UPDATE documentation_confluence_steps SET result=? WHERE job_id=? AND ordinal=?',(docs.dump(result),job_id,step['ordinal']))
        step['result']=result


def parent_id(page,plan,parents):
    if page['parentKey'] is None:return plan['parentPageId']
    parent=parents.get(page['parentKey'])
    if not parent:raise PublicationConflict('The parent page has not been confirmed.')
    return parent['id']


def guard_page(current,page,profile,parent,version=None,digest=None,title=None):
    if not current:raise PublicationConflict('The reviewed remote page is missing or no longer visible.')
    if current.get('type')!='page' or current.get('status')!='current' or current.get('space',{}).get('key')!=profile['spaceKey']:raise PublicationConflict('The destination is not a current page in the reviewed space.')
    ancestors=current.get('ancestors',[]);actual=str(ancestors[-1]['id']) if ancestors else None
    if actual!=parent:raise PublicationConflict('The destination hierarchy changed. No automatic move was performed.')
    if version is not None and current.get('version',{}).get('number')!=version:raise PublicationConflict('The page version changed after review. A fresh preview is required.')
    body=current.get('body',{}).get('storage',{}).get('value')
    if not isinstance(body,str):raise PublicationConflict('Storage representation is unavailable.')
    if digest is not None and sha(body)!=digest:raise PublicationConflict('Remote content changed after review; it was preserved.')
    if title is not None and current.get('title')!=title:raise PublicationConflict('The remote page title changed after review.')
    return body


def page_result(current,page,kept=False):
    return {'id':numeric(current['id']),'version':current['version']['number'],'hash':sha(current['body']['storage']['value']),
            'canonicalHash':page['contentHash'],'title':current['title'],'kept':kept}


def page_step(remote,job,plan,step,page,parents,owner,profile):
    parent=parent_id(page,plan,parents);operation='ntb-operation-'+step['operation_id']
    expected_body=marker(page['ownershipMarker'])+marker(operation)+page['storage']
    if step['recover']:
        known=step['result'].get('id')
        if known:candidates=[remote.page(known,optional=True)]
        elif page.get('remoteId'):candidates=[remote.page(page['remoteId'],optional=True)]
        else:candidates=[remote.page(p['id']) for p in remote.title_matches(page['title'])]
        matches=[p for p in candidates if p and has_marker(p.get('body',{}).get('storage',{}).get('value',''),operation) and has_marker(p['body']['storage']['value'],page['ownershipMarker'])]
        if not matches and page.get('remoteId') and len(candidates)==1 and candidates[0]:
            current=candidates[0]
            # An interrupted PUT can be repeated only against the exact original
            # version/hash. Its version CAS prevents a second successful update.
            guard_page(current,page,profile,parent,page['remoteVersion'],page['remoteHash'],page.get('remoteTitle'))
            step['recover']=False
            return page_step(remote,job,plan,step,page,parents,owner,profile)
        if len(matches)!=1:raise Uncertain('No unique page carrying this operation marker was found. Reconciliation may be retried; a create is never repeated blindly.')
        current=matches[0]
        stash(job['id'],step,owner,{'id':numeric(current['id'])})
        guard_page(current,page,profile,parent,version=(page['remoteVersion']+1) if page['remoteId'] else 1,title=page['title'])
        return 'succeeded',page_result(current,page)
    keep=page['key'] in plan['decisions']['keep']
    if page.get('remoteId'):
        current=remote.page(page['remoteId'],optional=True)
        body=guard_page(current,page,profile,parent,page['remoteVersion'],page['remoteHash'],page.get('remoteTitle'))
        if keep:return 'kept',page_result(current,page,True)
        collisions=remote.title_matches(page['title'])
        if any(str(p['id'])!=str(page['remoteId']) for p in collisions):raise PublicationConflict('A conflicting title appeared after review.')
        unchanged=page.get('planAction',page['action'])=='unchanged' and page['key'] not in plan['decisions']['replace']
        if unchanged:return 'skipped',page_result(current,page)
        payload={'id':str(page['remoteId']),'type':'page','title':page['title'],'space':{'key':profile['spaceKey']},
                 'version':{'number':page['remoteVersion']+1,'message':'net-toolbox:'+step['operation_id'],'minorEdit':True},
                 'body':{'storage':{'value':expected_body,'representation':'storage'}}}
        sent(job['id'],step,owner)
        response=remote.put_page(page['remoteId'],payload)
    else:
        if keep:raise PublicationConflict('An uncreated destination cannot be kept as a remote page.')
        if remote.title_matches(page['title']):raise PublicationConflict('The page title was claimed after preview; it was not adopted.')
        payload={'type':'page','title':page['title'],'space':{'key':profile['spaceKey']},'ancestors':[{'id':parent}] if parent else [],
                 'body':{'storage':{'value':expected_body,'representation':'storage'}}}
        sent(job['id'],step,owner)
        response=remote.create_page(payload)
    try:identifier=numeric(response['id'])
    except (KeyError,RemoteError):raise Uncertain('The successful write did not identify its page. Reconcile the operation marker.')
    stash(job['id'],step,owner,{'id':identifier})
    current=remote.page(identifier)
    guard_page(current,page,profile,parent,version=(page['remoteVersion']+1) if page['remoteId'] else 1,title=page['title'])
    if not has_marker(current['body']['storage']['value'],operation):raise Uncertain('Confluence did not retain the operation marker. The result requires reconciliation.')
    return 'succeeded',page_result(current,page)


def asset_step(remote,job,plan,step,page,parents,owner,profile):
    host=parents[page['key']];parent=parent_id(page,plan,parents)
    current=remote.page(host['id']);guard_page(current,page,profile,parent,host['version'],host['hash'],host['title'])
    asset=next(a for a in page['attachments'] if a['filename']==step['filename'])
    if host.get('kept'):return 'kept',{'pageId':host['id'],'reason':'Remote page and its attachments are preserved.'}
    existing=[a for a in remote.attachments(host['id']) if a['title']==asset['filename']]
    if asset['action']=='unchanged' and not step['recover']:
        if len(existing)!=1 or str(existing[0]['id'])!=asset['remoteId'] or existing[0].get('version',{}).get('number')!=asset['remoteVersion']:raise PublicationConflict('The unchanged attachment changed after preview.')
        found=existing[0]
    elif step['recover']:
        if len(existing)!=1:raise Uncertain('The upload result is not visible uniquely; reconciliation did not repeat it.')
        found=existing[0]
        comment=found.get('metadata',{}).get('comment') or found.get('version',{}).get('message')
        if comment!='net-toolbox:'+step['operation_id']:raise Uncertain('The attachment has no matching upload operation marker; it was not adopted.')
        if found.get('version',{}).get('number')!=1:raise PublicationConflict('The uploaded attachment was edited externally.')
    else:
        if asset['action']!='create':raise PublicationConflict('Binary attachment updates are not overwritten in place. Create a fresh content-addressed asset or keep the remote page.')
        if existing:raise PublicationConflict('An attachment filename was claimed after review.')
        with docs.connection() as conn:
            data=conn.execute('SELECT artifact FROM documentation_dc_versions WHERE document_id=? AND number=?',(job['document_id'],job['version_number'])).fetchone()[0]
        with zipfile.ZipFile(io.BytesIO(data)) as archive:content=archive.read(asset['path'])
        if sha(content)!=asset['sha256']:raise PublicationConflict('The frozen attachment checksum does not match the reviewed plan.')
        sent(job['id'],step,owner)
        remote.upload(host['id'],asset['filename'],content,step['operation_id'])
        existing=[a for a in remote.attachments(host['id']) if a['title']==asset['filename']]
        if len(existing)!=1:raise Uncertain('The upload response could not be verified in the attachment collection.')
        found=existing[0]
        stash(job['id'],step,owner,{'id':numeric(found['id']),'pageId':host['id']})
    identifier=numeric(found['id']);version=found.get('version',{}).get('number')
    if asset['action']=='create':
        if version!=1:raise PublicationConflict('The new attachment changed externally before confirmation.')
        if (found.get('metadata',{}).get('comment') or found.get('version',{}).get('message'))!='net-toolbox:'+step['operation_id']:raise Uncertain('The upload ownership marker could not be verified.')
    if not isinstance(version,int) or sha(remote.binary(host['id'],asset['filename'],version))!=asset['sha256']:raise PublicationConflict('Attachment bytes differ from the frozen document. The remote file was preserved.')
    return ('skipped' if asset['action']=='unchanged' else 'succeeded'),{'id':identifier,'pageId':host['id'],'version':version,'sha256':asset['sha256'],'filename':asset['filename']}


def verify_step(remote,job,plan,step,page,parents,profile):
    host=parents[page['key']]
    current=remote.page(host['id']);guard_page(current,page,profile,parent_id(page,plan,parents),host['version'],host['hash'],host['title'])
    if host.get('kept'):return 'kept',host
    if not page.get('remoteId'):
        restrictions=remote.get(f'rest/api/content/{host["id"]}/restriction/byOperation/read',{'expand':'restrictions.user,restrictions.group'})
        for kind in ('user','group'):
            data=restrictions.get('restrictions',{}).get(kind)
            if not isinstance(data,dict) or data.get('results') or data.get('_links',{}).get('next'):raise PublicationConflict('Read restrictions on the newly created page differ from inherited audience settings.')
    existing={str(a['id']):a for a in remote.attachments(host['id'])}
    with docs.connection() as conn:
        records=conn.execute("SELECT filename,result FROM documentation_confluence_steps WHERE job_id=? AND page_key=? AND kind='asset' AND status IN ('succeeded','skipped')",(job['id'],page['key'])).fetchall()
    for record in records:
        asset=json.loads(record['result']);found=existing.get(asset['id'])
        if not found or found['title']!=record['filename'] or found.get('version',{}).get('number')!=asset['version']:raise PublicationConflict('An attachment changed before final link verification.')
        if not any(n.attrib.get('{urn:ri}filename')==record['filename'] for n in ET.fromstring('<root xmlns:ac="urn:ac" xmlns:ri="urn:ri">'+current['body']['storage']['value']+'</root>').iter('{urn:ri}attachment')):raise PublicationConflict('A published PNG reference did not survive storage rendering.')
    return 'succeeded',host


def finish(job,step,owner,status,result,actor,error=None,retry_at=0):
    with docs.connection(True) as conn:
        live=conn.execute('SELECT lease_owner FROM documentation_confluence_jobs WHERE id=?',(job['id'],)).fetchone()
        if not live or live[0]!=owner:raise docs.Conflict()
        conn.execute('UPDATE documentation_confluence_steps SET status=?,result=?,error_code=?,error_message=?,updated_at=? WHERE job_id=? AND ordinal=?',
                     (status,docs.dump(result),error[0] if error else None,error[1] if error else None,docs.now(),job['id'],step['ordinal']))
        plan=json.loads(job['payload'])
        if status in jobs.DONE and step['kind']=='page':
            page=next(p for p in plan['pages'] if p['key']==step['page_key'])
            conn.execute('''UPDATE documentation_confluence_pages SET remote_id=?,remote_version=?,last_published_revision=?,
                last_published_hash=?,last_remote_hash=?,preserve_remote=? WHERE id=?''',
                (result['id'],result['version'],job['version_number'],None if result.get('kept') else page['contentHash'],result['hash'],int(result.get('kept',False)),page['destinationId']))
        if status=='conflict' and step['kind']=='page' and result.get('id'):
            page=next(p for p in plan['pages'] if p['key']==step['page_key'])
            conn.execute('UPDATE documentation_confluence_pages SET remote_id=COALESCE(remote_id,?),last_published_revision=COALESCE(last_published_revision,?) WHERE id=?',
                         (result['id'],job['version_number'],page['destinationId']))
        if status in jobs.DONE and step['kind']=='asset' and result.get('id'):
            page=next(p for p in plan['pages'] if p['key']==step['page_key'])
            old=json.loads(conn.execute('SELECT last_attachments FROM documentation_confluence_pages WHERE id=?',(page['destinationId'],)).fetchone()[0])
            old[step['filename']]={k:result[k] for k in ('id','version','sha256')}
            conn.execute('UPDATE documentation_confluence_pages SET last_attachments=? WHERE id=?',(docs.dump(old),page['destinationId']))
        remaining=conn.execute("SELECT COUNT(*) FROM documentation_confluence_steps WHERE job_id=? AND status NOT IN ('succeeded','skipped','kept')",(job['id'],)).fetchone()[0]
        state=('succeeded' if not remaining else 'pending') if status in jobs.DONE else status
        conn.execute('UPDATE documentation_confluence_jobs SET status=?,active=?,revision=revision+1,lease_owner=NULL,lease_until=0,retry_at=?,updated_at=? WHERE id=?',
                     (state,int(state!='succeeded'),retry_at,docs.now(),job['id']))
        profiles.audit(conn,job['profile_id'],actor,'publication_step',{'jobId':job['id'],'step':step['ordinal'],'kind':step['kind'],'status':status,'remoteId':result.get('id'),'code':error[0] if error else None},job['document_id'])
        return jobs.detail(conn,job['id'],job['document_id'],job['version_number'])


def advance(job_id,identifier,number,expected,actor):
    job,step,owner,parents=claim(job_id,identifier,number,expected,actor)
    if step is None:return jobs.get(job_id,identifier,number)
    plan=json.loads(job['payload'])
    page=next((p for p in plan['pages'] if p['key']==step['page_key']),None)
    try:
        profile,credential=profiles.load(job['profile_id'],plan['profileVersion'])
        with PublishingClient(profile,credential) as remote:
            if sha(docs.dump(capture(remote,plan['pages'])))!=plan['audienceHash']:raise PublicationConflict('Destination read permissions changed after preview. Prepare a fresh audience review.')
            # Profile edits are checked again after remote reads, before each write.
            profiles.load(job['profile_id'],plan['profileVersion'])
            if step['kind']=='page':status,result=page_step(remote,job,plan,step,page,parents,owner,profile)
            elif step['kind']=='asset':status,result=asset_step(remote,job,plan,step,page,parents,owner,profile)
            elif step['kind']=='verify':status,result=verify_step(remote,job,plan,step,page,parents,profile)
            else:status,result='succeeded',{'audienceVerifiedAt':docs.now(),'audienceConfirmedBy':job['actor_id']}
        return finish(job,step,owner,status,result,actor)
    except (docs.Conflict,docs.Invalid) as exc:
        return finish(job,step,owner,'uncertain' if step['recover'] else 'conflict',step['result'],actor,('profile_changed','The connection changed or became unavailable. Review a fresh preview before further writes.'))
    except WriteError as exc:
        state='uncertain' if exc.uncertain else 'conflict' if exc.code in ('conflict','rejected') else 'failed'
        return finish(job,step,owner,state,step['result'],actor,(exc.code,exc.message),time.time()+exc.retry_after if exc.retry_after else 0)
    except Uncertain as exc:return finish(job,step,owner,'uncertain',step['result'],actor,('uncertain',str(exc)))
    except PublicationConflict as exc:return finish(job,step,owner,'conflict',step['result'],actor,('conflict',str(exc)))
    except RemoteError as exc:
        # A read failure after the durable send marker is still ambiguous.
        with docs.connection() as conn:was_sent=conn.execute('SELECT sent FROM documentation_confluence_steps WHERE job_id=? AND ordinal=?',(job_id,step['ordinal'])).fetchone()[0]
        return finish(job,step,owner,'uncertain' if was_sent else 'failed',step['result'],actor,(exc.code,exc.message))


def revalidate(job_id,identifier,number,expected,profile_version,actor):
    with docs.connection() as conn:
        job=jobs.row(conn,job_id,identifier,number)
        if job['revision']!=expected:raise docs.Conflict()
        if job['lease_until']>time.time() or job['status'] in jobs.TERMINAL:raise docs.StateConflict('Wait for the current operation or select an unfinished publication.')
        plan=json.loads(job['payload'])
    profile,credential=profiles.load(job['profile_id'],profile_version)
    if any(profile[key]!=plan[key] for key in ('baseUrl','spaceKey','parentPageId')):raise docs.Invalid('The original publication destination must remain unchanged.')
    with PublishingClient(profile,credential) as remote:
        remote.probe()
        if sha(docs.dump(capture(remote,plan['pages'])))!=plan['audienceHash']:raise docs.Invalid('The destination audience changed. Abandon known results and review a fresh preview.')
    with docs.connection(True) as conn:
        current=jobs.row(conn,job_id,identifier,number)
        if current['revision']!=expected or current['lease_until']>time.time() or profiles.row(conn,job['profile_id'])['version']!=profile_version:raise docs.Conflict()
        plan['profileVersion']=profile_version
        conn.execute("UPDATE documentation_confluence_jobs SET payload=?,status='paused',revision=revision+1,updated_at=? WHERE id=?",(docs.dump(plan),docs.now(),job_id))
        conn.execute("UPDATE documentation_confluence_steps SET status='pending',sent=0 WHERE job_id=? AND error_code='profile_changed' AND status='conflict'",(job_id,))
        profiles.audit(conn,job['profile_id'],actor,'revalidate_publication',{'jobId':job_id,'profileVersion':profile_version,'audienceConfirmed':True},identifier)
        return jobs.detail(conn,job_id,identifier,number)


def resolve(job_id,identifier,number,request,actor):
    with docs.connection() as conn:
        job=jobs.row(conn,job_id,identifier,number)
        if job['revision']!=request.expectedRevision:raise docs.Conflict()
        if job['lease_until']>time.time() or job['status'] in jobs.TERMINAL:raise docs.StateConflict('Wait for the active request before resolving an uncertain result.')
        step=conn.execute("SELECT * FROM documentation_confluence_steps WHERE job_id=? AND status IN ('uncertain','inflight') ORDER BY ordinal LIMIT 1",(job_id,)).fetchone()
        if step is None:raise docs.Invalid('This publication has no uncertain write to resolve.')
        step=dict(step);plan=json.loads(job['payload']);page=next(p for p in plan['pages'] if p['key']==step['page_key'])
        parents=step_map(conn,job_id)
    profile,credential=profiles.load(job['profile_id'],plan['profileVersion'])
    with PublishingClient(profile,credential) as remote:
        if request.remotePageId:
            if step['kind']!='page':raise docs.Invalid('A page ID can resolve a page operation only.')
            if page.get('remoteId') and request.remotePageId!=page['remoteId']:raise docs.Invalid('An existing mapped page cannot be rebound to another page ID.')
            current=remote.page(request.remotePageId)
            body=current.get('body',{}).get('storage',{}).get('value','')
            if not has_marker(body,'ntb-operation-'+step['operation_id']) or not has_marker(body,page['ownershipMarker']):raise docs.Invalid('This remote page does not carry this publication operation and ownership markers.')
            result={'id':request.remotePageId}
        elif request.notAppliedConfirmed:
            if step['kind']=='page':
                if page.get('remoteId'):raise docs.Invalid('Interrupted updates use a version-checked reconciliation, not a manual reset.')
                if remote.title_matches(page['title']):raise docs.Invalid('The title is visible remotely; reconcile its identity instead of repeating the create.')
            elif step['kind']=='asset':
                if any(a['title']==step['filename'] for a in remote.attachments(parents[page['key']]['id'])):raise docs.Invalid('The filename exists remotely; reconcile it instead of repeating the upload.')
            else:raise docs.Invalid('Only an uncertain create/upload may be manually reset.')
            result={}
        else:raise docs.Invalid('Provide a marked remote page ID or explicitly confirm that the write was not applied.')
    with docs.connection(True) as conn:
        current=jobs.row(conn,job_id,identifier,number)
        if current['revision']!=request.expectedRevision or current['lease_until']>time.time():raise docs.Conflict()
        conn.execute('UPDATE documentation_confluence_steps SET result=?,status=?,sent=?,error_code=NULL,error_message=NULL WHERE job_id=? AND ordinal=?',
                     (docs.dump(result),'uncertain' if request.remotePageId else 'pending',int(bool(request.remotePageId)),job_id,step['ordinal']))
        conn.execute("UPDATE documentation_confluence_jobs SET status='paused',revision=revision+1,updated_at=? WHERE id=?",(docs.now(),job_id))
        profiles.audit(conn,job['profile_id'],actor,'resolve_publication',{'jobId':job_id,'step':step['ordinal'],'remotePageId':request.remotePageId,'notAppliedConfirmed':request.notAppliedConfirmed},identifier)
        return jobs.detail(conn,job_id,identifier,number)
