from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field, ConfigDict
import auth_db
from . import access


class GroupCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1,max_length=120)
    source: Literal['local','ad']
    groupDn: str | None = Field(default=None,max_length=2048)


def invoke(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(404 if str(exc).endswith('not found') else 400,str(exc))


def build_router(require_platform_admin):
    router = APIRouter(prefix='/api/admin/access-groups',tags=['access-groups'])
    def admin(user=Depends(require_platform_admin)):
        if user is None:
            raise HTTPException(401,'Sign in as a platform administrator')
        return user
    router.dependencies.append(Depends(admin))

    @router.get('')
    def groups(query: str = Query('',max_length=120), limit: int = Query(25,ge=1,le=100), offset: int = Query(0,ge=0)):
        return access.groups(query.strip(),limit,offset)

    @router.get('/accounts')
    def accounts(query: str = Query('',max_length=120), limit: int = Query(25,ge=1,le=100), offset: int = Query(0,ge=0)):
        conn=auth_db.get_connection()
        try:
            term='%'+query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
            where="WHERE username LIKE ? ESCAPE '\\'"
            total=conn.execute('SELECT COUNT(*) FROM users '+where,(term,)).fetchone()[0]
            rows=conn.execute('SELECT id,username,auth_source AS authSource FROM users '+where+' ORDER BY username,id LIMIT ? OFFSET ?',(term,limit,offset))
            return {'items':[dict(row) for row in rows],'total':total,'offset':offset,'limit':limit}
        finally:
            conn.close()

    @router.get('/audit')
    def audit(limit: int = Query(25,ge=1,le=100), offset: int = Query(0,ge=0)):
        conn=auth_db.get_connection()
        try:
            where="WHERE a.tenant_id IS NULL AND a.action LIKE 'group_%'"
            total=conn.execute('SELECT COUNT(*) FROM tenant_audit a '+where).fetchone()[0]
            rows=conn.execute('SELECT a.*,u.username AS actor_username FROM tenant_audit a LEFT JOIN users u ON u.id=a.actor_id '+where+' ORDER BY a.id DESC LIMIT ? OFFSET ?',(limit,offset))
            return {'items':[dict(row) for row in rows],'total':total,'limit':limit,'offset':offset}
        finally:
            conn.close()

    @router.post('',status_code=201)
    def create(req: GroupCreate,user=Depends(admin)):
        return invoke(access.create_group,req.name,req.source,req.groupDn,user['id'])

    @router.delete('/{group_id}')
    def delete(group_id: int = Path(ge=1),user=Depends(admin)):
        invoke(access.delete_group,group_id,user['id'])
        return {'ok':True}

    @router.get('/{group_id}/members')
    def members(group_id: int = Path(ge=1),limit: int = Query(25,ge=1,le=100),offset: int = Query(0,ge=0)):
        return invoke(access.members,group_id,limit,offset)

    @router.put('/{group_id}/members/{user_id}')
    def add_member(group_id: int = Path(ge=1),user_id: int = Path(ge=1),user=Depends(admin)):
        invoke(access.member_change,group_id,user_id,user['id'])
        return {'ok':True}

    @router.delete('/{group_id}/members/{user_id}')
    def remove_member(group_id: int = Path(ge=1),user_id: int = Path(ge=1),user=Depends(admin)):
        invoke(access.member_change,group_id,user_id,user['id'],remove=True)
        return {'ok':True}

    return router
