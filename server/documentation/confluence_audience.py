"""Read-only audience snapshots shared by preview and execution."""
import json
from urllib.parse import quote
from .confluence_client import RemoteError


def capture(remote,pages):
    space=remote.get('rest/api/space/'+quote(remote.profile['spaceKey'],safe=''),{'expand':'permissions'})
    ids={p['remoteId'] for p in pages if p.get('remoteId')}
    if remote.profile['parentPageId']:ids.add(remote.profile['parentPageId'])
    expanded=set(ids)
    # Managed parents are already present among the planned page IDs. Only the
    # configured external parent contributes ancestors outside that hierarchy.
    if remote.profile['parentPageId']:
        page=remote.page(remote.profile['parentPageId'],optional=True)
        if page:expanded.update(str(parent['id']) for parent in page.get('ancestors',[]))
    restrictions=[]
    for identifier in sorted(expanded):
        result=remote.get(f'rest/api/content/{str(int(identifier))}/restriction/byOperation/read',{'expand':'restrictions.user,restrictions.group'},optional=True)
        if result is None:
            restrictions.append({'pageId':identifier,'unavailable':True});continue
        entries={}
        for kind in ('user','group'):
            group=result.get('restrictions',{}).get(kind)
            if not isinstance(group,dict) or not isinstance(group.get('results'),list):raise RemoteError('audience','Confluence did not expose complete read restrictions.')
            if group.get('_links',{}).get('next'):raise RemoteError('audience','Read restrictions exceed the supported response window; no publication was started.')
            entries[kind]=sorted(str(x.get('userKey') or x.get('username') or x.get('name') or x.get('accountId')) for x in group['results'])
        restrictions.append({'pageId':identifier,**entries})
    # IDs/names/operations only; never retain arbitrary API bodies in the plan.
    permissions=space.get('permissions')
    normalized=[]
    if isinstance(permissions,list):
        for item in permissions:
            normalized.append({'operation':item.get('operation'), 'subjects':item.get('subjects'), 'anonymousAccess':item.get('anonymousAccess'), 'unlicensedAccess':item.get('unlicensedAccess')})
    return {'spaceKey':remote.profile['spaceKey'],'spacePermissionsReported':isinstance(permissions,list),
            'spacePermissions':sorted(normalized,key=lambda x:json.dumps(x,sort_keys=True)), 'pageRestrictions':restrictions,
            'note':'Space permissions and inherited page read restrictions. The publisher must confirm the intended audience; tenant and Confluence groups are not assumed equivalent.'}
