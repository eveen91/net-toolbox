"""Read-only remote inspection and tenant-local, reviewable publication plans.

There are intentionally no remote create/update/upload/delete operations here.
"""
import difflib
import io
import json
import uuid
import zipfile
from . import access,confluence_profiles as profiles,repository as documents
from .confluence_client import Client,RemoteError
from .confluence_render import render,sha,RENDERER_VERSION

MAX_PREVIEW_BYTES=32*1024*1024


def check(identifier,expected,actor):
    profile,credential=profiles.load(identifier,expected)
    result={'checkedAt':documents.now(),'profileVersion':expected,'profileName':profile['name']}
    try:
        with Client(profile,credential) as remote:result.update(ok=True,**remote.probe())
    except RemoteError as exc:result.update(ok=False,code=exc.code,message=exc.message)
    with documents.connection(True) as conn:
        current=profiles.row(conn,identifier)
        if current['version']!=expected:raise documents.Conflict()
        conn.execute('UPDATE documentation_confluence_profiles SET last_check=? WHERE id=?',(documents.dump(result),identifier))
        profiles.audit(conn,identifier,actor,'check_connection',{'ok':result['ok'],'profileVersion':expected,'code':result.get('code')})
    return result


def diff(before,after):
    lines=list(difflib.unified_diff(before.replace('><','>\n<').splitlines(),after.replace('><','>\n<').splitlines(),fromfile='Confluence now',tofile='Planned content',lineterm=''))
    return '\n'.join(lines[:2000]),len(lines)>2000


def mappings(conn,profile_id,identifier):
    return {row['page_key']:dict(row) for row in conn.execute('SELECT * FROM documentation_confluence_pages WHERE profile_id=? AND document_id=?',(profile_id,identifier))}


def attachment_plan(proposed,existing,baseline):
    by_title={}
    for item in existing:by_title.setdefault(item.get('title'),[]).append(item)
    output=[]
    for item in proposed:
        asset={**item,'action':'create','remoteId':None,'remoteVersion':None,'issues':[]}
        matches=by_title.get(item['filename'],[]);owned=baseline.get(item['filename'])
        if len(matches)>1:asset['issues'].append('Multiple attachments share this filename.')
        elif matches:
            remote=matches[0];number=remote.get('version',{}).get('number')
            asset.update(remoteId=str(remote.get('id','')),remoteVersion=number)
            if not owned:asset['issues'].append('Attachment filename exists without an application ownership baseline; it will not be adopted or overwritten.')
            elif str(owned.get('id'))!=asset['remoteId'] or owned.get('version')!=number:asset['issues'].append('Attachment changed externally since the recorded publication.')
            else:asset['action']='unchanged' if owned.get('sha256')==item['sha256'] else 'update'
        elif owned:asset['issues'].append('A previously published attachment is missing; inspect the deletion before re-creating it.')
        if asset['issues']:asset['action']='conflict'
        output.append(asset)
    return output


def inspect(page,remote,profile,saved,all_saved):
    baseline=saved.get(page['key']);remote_id=baseline.get('remote_id') if baseline else None
    page.update(remoteTitle=None,action='create',remoteId=remote_id,remoteVersion=None,issues=[],advisories=[],destinationUrl=None,remoteHash=None,diff='',diffTruncated=False)
    current=remote.page(remote_id,optional=True) if remote_id else None
    collisions=remote.title_matches(page['title'])
    if any(str(row.get('id'))!=str(remote_id) for row in collisions):page['issues'].append('The destination title already exists without this stable page mapping; it will not be adopted by title.')
    if remote_id and current is None:page['issues'].append('The mapped remote page is missing or no longer visible. It will not be re-created automatically.')
    if current:
        page['destinationUrl']=profile['baseUrl']+'/pages/viewpage.action?pageId='+str(remote_id)
        page['remoteVersion']=current.get('version',{}).get('number')
        page['remoteTitle']=current.get('title')
        content=current.get('body',{}).get('storage',{}).get('value')
        if not isinstance(content,str):raise RemoteError('storage','Mapped page did not provide its storage representation.')
        page['remoteHash']=sha(content)
        if current.get('space',{}).get('key')!=profile['spaceKey'] or current.get('status')!='current' or current.get('type')!='page':page['issues'].append('The mapped destination is not a current page in the configured space.')
        if not baseline.get('last_remote_hash') or not baseline.get('remote_version'):page['issues'].append('The remote page has no verified publication baseline.')
        elif page['remoteVersion']!=baseline['remote_version'] or page['remoteHash']!=baseline['last_remote_hash']:page['issues'].append('Remote content or version changed externally after the last recorded publication.')
        ancestors=current.get('ancestors',[])
        parent=str(ancestors[-1]['id']) if ancestors else None
        desired_parent=profile['parentPageId'] if page['parentKey'] is None else (all_saved.get(page['parentKey']) or {}).get('remote_id')
        if (page['parentKey'] is not None and not desired_parent) or parent!=desired_parent:page['issues'].append('The page hierarchy differs from the planned destination; automatic moves are not allowed.')
        operations=current.get('operations')
        if isinstance(operations,list):
            if not any(op.get('operation') in ('update','administer') for op in operations if isinstance(op,dict)):page['issues'].append('Confluence did not grant page update access to the service identity.')
        else:page['advisories'].append('Page update privileges were not reported by this API; actual writes remain unverified.')
        page['action']='unchanged' if page['contentHash']==baseline.get('last_published_hash') and current.get('title')==page['title'] else 'update'
        if page['action']=='unchanged' and page['remoteHash']!=page['contentHash']:
            page['advisories'].append('Confluence normalized the stored markup. The canonical content and recorded remote baseline are unchanged.')
        page['attachments']=attachment_plan(page['attachments'],remote.attachments(remote_id),json.loads(baseline['last_attachments']))
        page['diff'],page['diffTruncated']=diff(content,page['storage'])
    else:
        page['attachments']=attachment_plan(page['attachments'],[],{})
        page['diff'],page['diffTruncated']=diff('',page['storage'])
    if any(asset['action']=='conflict' for asset in page['attachments']):page['issues'].append('One or more attachments require conflict review.')
    if page['issues']:page['action']='conflict'
    elif baseline and baseline.get('preserve_remote'):
        page['action']='keep';page['advisories'].append('Remote content is explicitly preserved. Publication will not replace this page or its attachments.')

    page['planAction']=page['action']


def prepare(identifier,number,profile_id,expected,actor):
    access.action('publish')
    profile,credential=profiles.load(profile_id,expected)
    with documents.connection() as conn:
        version=documents.version_detail(conn,identifier,number)
        if version['kind']!='published':raise documents.Invalid('Choose an immutable locally published version before preparing Confluence publication.')
        document=version['document']
        blob=conn.execute('SELECT artifact FROM documentation_dc_versions WHERE document_id=? AND number=?',(identifier,number)).fetchone()[0]
        saved=mappings(conn,profile_id,identifier)
        baseline_versions=sorted({row['last_published_revision'] for row in saved.values() if row['remote_id'] and row['last_published_revision']})
        if any(row['remote_id'] and not row['last_published_revision'] for row in saved.values()):raise documents.Invalid('A mapped destination lacks its local publication baseline. Restore the mapping record before inspecting remote content.')
        required=set(document.get('snapshot',{}).get('requiredPermissions',[]))
        for baseline_number in baseline_versions:
            baseline=documents.version_detail(conn,identifier,baseline_number)
            required.update(baseline['document'].get('snapshot',{}).get('requiredPermissions',[]))
    try:pages=render(document,number,profile['spaceKey'])
    except ValueError as exc:raise documents.Invalid(str(exc)) from exc
    # Use frozen bytes, not the live diagram renderer or live source adapters.
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        manifest=json.loads(archive.read('manifest.json'))
        file_meta={f['path']:f for f in manifest['files']}
        for page in pages:
            for asset in page['attachments']:
                data=archive.read(asset['path']);digest=sha(data)
                if asset['path'] not in file_meta or file_meta[asset['path']]['sha256']!=digest:raise documents.Invalid('A frozen attachment failed its checksum. Restore the original revision backup.')
                asset.update(sha256=digest,bytes=len(data))
    with Client(profile,credential) as remote:
        compatibility=remote.probe()
        for page in pages:inspect(page,remote,profile,saved,saved)
        from .confluence_audience import capture
        audience=capture(remote,pages)
    blocked=set()
    for page in pages:
        if page['parentKey'] in blocked:
            page['issues'].append('A parent page has a conflict; this descendant cannot be published independently.')
            page['action']='conflict'
        if page['issues']:blocked.add(page['key'])
    retained=[{'key':key,'remoteId':row['remote_id'],'action':'retain','reason':'No longer in the planned hierarchy; remote pages are never deleted automatically.'} for key,row in saved.items() if key not in {p['key'] for p in pages} and row['remote_id']]
    preview_id=str(uuid.uuid4());stamp=documents.now()
    result={'id':preview_id,'documentId':identifier,'version':number,'profileId':profile_id,'profileVersion':expected,'profileName':profile['name'],
            'baseUrl':profile['baseUrl'],'spaceKey':profile['spaceKey'],'parentPageId':profile['parentPageId'],
            'createdAt':stamp,'rendererVersion':RENDERER_VERSION,'baselineVersions':baseline_versions,'requiredPermissions':sorted(required),'compatibility':compatibility,'pages':pages,'retainedPages':retained,
            'audience':audience,'audienceHash':sha(documents.dump(audience)),'hasConflicts':bool(blocked),'readOnly':True,'remoteWritesPerformed':False,
            'advisories':['No pages or attachments were changed while capturing this preview. Publication results are recorded separately below. Regenerate the preview after remote changes.',
                          'Page creation/upload permissions and the intended reader audience still need verification before publication.']}
    with documents.connection(True) as conn:
        documents.version_detail(conn,identifier,number)
        if profiles.row(conn,profile_id)['version']!=expected:raise documents.Conflict()
        current=mappings(conn,profile_id,identifier)
        for key,value in saved.items():
            if current.get(key)!=value:raise documents.Conflict()
        for page in pages:
            existing=current.get(page['key'])
            if existing and page['key'] not in saved and existing['remote_id']:raise documents.Conflict()
            if not existing:
                local_id=str(uuid.uuid4())
                conn.execute('INSERT INTO documentation_confluence_pages(id,profile_id,document_id,page_key,created_at) VALUES(?,?,?,?,?)',(local_id,profile_id,identifier,page['key'],stamp))
            else:local_id=existing['id']
            page['destinationId']=local_id
            page['ownershipMarker']='ntb-owned-'+local_id
        serialized=documents.dump(result)
        if len(serialized.encode())>MAX_PREVIEW_BYTES:raise documents.Invalid('The Confluence preview exceeds 32 MiB. Choose a smaller scope.')
        conn.execute('INSERT INTO documentation_confluence_previews(id,profile_id,document_id,version_number,profile_version,payload,actor_id,created_at,required_permissions) VALUES(?,?,?,?,?,?,?,?,?)',
                     (preview_id,profile_id,identifier,number,expected,serialized,actor,stamp,documents.dump(sorted(required))))
        profiles.audit(conn,profile_id,actor,'prepare_preview',{'id':preview_id,'version':number,'pages':len(pages),'hasConflicts':bool(blocked),'profileVersion':expected},identifier)
    return result


def get(preview_id,identifier,number):
    access.action('publish')
    with documents.connection() as conn:
        documents.version_detail(conn,identifier,number)
        row=conn.execute('SELECT * FROM documentation_confluence_previews WHERE id=? AND document_id=? AND version_number=?',(preview_id,identifier,number)).fetchone()
        if row is None:raise documents.Missing()
        access.check(json.loads(row['required_permissions']))
        result=json.loads(row['payload'])
        for baseline_number in result.get('baselineVersions',[]):documents.version_detail(conn,identifier,baseline_number)
        profile=profiles.public(profiles.row(conn,row['profile_id']))
        result['profileChanged']=profile['version']!=row['profile_version'] or not profile['enabled']
        return result


def listing(identifier,number,limit,offset):
    access.action('publish')
    with documents.connection() as conn:
        documents.version_detail(conn,identifier,number)
        clause,params=documents.permission_clause()
        where='p.document_id=? AND p.version_number=? AND ('+clause+')'
        values=(identifier,number,*params)
        total=conn.execute('SELECT COUNT(*) FROM documentation_confluence_previews p WHERE '+where,values).fetchone()[0]
        rows=conn.execute("""SELECT p.id,p.created_at AS createdAt,p.profile_id AS profileId,c.name AS profileName,
            p.profile_version AS profileVersion,json_extract(p.payload,'$.hasConflicts') AS hasConflicts
            FROM documentation_confluence_previews p JOIN documentation_confluence_profiles c ON c.id=p.profile_id
            WHERE """+where+' ORDER BY p.created_at DESC,p.id DESC LIMIT ? OFFSET ?',(*values,limit,offset))
        return {'items':[dict(row) for row in rows],'total':total,'limit':limit,'offset':offset}
