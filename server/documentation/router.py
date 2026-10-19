import sqlite3
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Path,Query,Response
from . import repository as repo,access,sources,templates,options
from .schemas import DCForm,SaveDC,CreateVersion,Expected,Transition,Refresh,Coverage


def invoke(operation,*args,permissions=None):
    try:
        with access.scoped(permissions if permissions is not None else {'*'}):return operation(*args)
    except repo.Missing:raise HTTPException(404,'Document, revision or linked infrastructure record not found')
    except repo.Conflict:raise HTTPException(409,'This document changed. Reopen the saved document before retrying; your entered values remain in the form.')
    except repo.VersionExists:raise HTTPException(409,'A version already exists for this saved draft. Save further changes before creating another version.')
    except repo.Invalid as exc:raise HTTPException(422,exc.args[0])
    except repo.StateConflict as exc:raise HTTPException(409,str(exc))
    except access.Denied as exc:raise HTTPException(403,str(exc))
    except sqlite3.OperationalError:raise HTTPException(503,'Documentation storage is unavailable. Retry shortly; your entered values remain in the form.')


def coverage(req):
    with repo.connection() as conn:return sources.collect(conn,req.scopeSpec.model_dump(),req.templateId)


def build_router(require_feature,require_logged_in_user):
    def grants(user=Depends(require_logged_in_user)):
        values=access.permissions(user)
        if not access.allowed(['documentation.read'],values):raise HTTPException(403,'Documentation Read permission is required.')
        return values
    router=APIRouter(prefix='/api/documentation/dc',tags=['documentation'],dependencies=[Depends(grants)])

    from .confluence_router import build_router as confluence_router
    router.include_router(confluence_router(grants,require_logged_in_user,invoke))

    @router.get('/templates')
    def catalog():return templates.TEMPLATES

    @router.get('/options')
    def choices(kind:Literal['dc','rack','device','subnet','dhcp'],query:str=Query('',max_length=100),deviceType:Literal['switch','firewall']|None=None,limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),permissions=Depends(grants)):
        return invoke(options.listing,kind,query,deviceType,limit,offset,permissions=permissions)

    @router.post('/coverage')
    def preview_coverage(req:Coverage,permissions=Depends(grants)):
        return invoke(coverage,req,permissions=permissions)

    @router.get('')
    def listing(limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),query:str=Query('',max_length=100),status:Literal['draft','review','published']|None=None,template:Literal['network','switch','firewall','runbook']|None=None,permissions=Depends(grants)):
        return invoke(repo.listing,limit,offset,query,status,template,permissions=permissions)

    @router.get('/{identifier}')
    def detail(identifier:int=Path(ge=1),permissions=Depends(grants)):return invoke(repo.get,identifier,permissions=permissions)

    @router.post('',status_code=201)
    def create(req:DCForm,user=Depends(require_logged_in_user),permissions=Depends(grants)):
        return invoke(repo.save,req.model_dump(),user['id'] if user else None,permissions=permissions)

    @router.put('/{identifier}')
    def update(req:SaveDC,identifier:int=Path(ge=1),user=Depends(require_logged_in_user),permissions=Depends(grants)):
        return invoke(repo.save,req.model_dump(exclude={'expectedVersion'}),user['id'] if user else None,identifier,req.expectedVersion,permissions=permissions)

    @router.get('/{identifier}/validation')
    def validation(identifier:int=Path(ge=1),permissions=Depends(grants)):
        return invoke(lambda:repo.get(identifier)['validation'],permissions=permissions)

    @router.post('/{identifier}/transition')
    def transition(req:Transition,identifier:int=Path(ge=1),user=Depends(require_logged_in_user),permissions=Depends(grants)):
        return invoke(repo.transition,identifier,req.expectedVersion,req.action,req.description,user,permissions=permissions)

    @router.post('/{identifier}/refresh/preview')
    def refresh_preview(req:Expected,identifier:int=Path(ge=1),permissions=Depends(grants)):
        return invoke(repo.source_preview,identifier,req.expectedVersion,permissions=permissions)

    @router.post('/{identifier}/refresh')
    def refresh(req:Refresh,identifier:int=Path(ge=1),user=Depends(require_logged_in_user),permissions=Depends(grants)):
        return invoke(repo.refresh,identifier,req.expectedVersion,req.snapshotDigest,user['id'] if user else None,permissions=permissions)

    @router.get('/{identifier}/compare')
    def compare(identifier:int=Path(ge=1),before:int=Query(ge=1),after:int=Query(ge=1),permissions=Depends(grants)):
        return invoke(repo.compare,identifier,before,after,permissions=permissions)

    @router.get('/{identifier}/history')
    def history(identifier:int=Path(ge=1),limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),permissions=Depends(grants)):
        return invoke(repo.history,identifier,limit,offset,permissions=permissions)

    @router.get('/{identifier}/versions')
    def versions(identifier:int=Path(ge=1),limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),permissions=Depends(grants)):
        return invoke(repo.versions,identifier,limit,offset,permissions=permissions)

    @router.post('/{identifier}/versions',status_code=201)
    def create_version(req:CreateVersion,identifier:int=Path(ge=1),user=Depends(require_logged_in_user),permissions=Depends(grants)):
        return invoke(repo.create_version,identifier,req.expectedVersion,req.description,user,permissions=permissions)

    @router.get('/{identifier}/versions/{number}')
    def version(identifier:int=Path(ge=1),number:int=Path(ge=1),permissions=Depends(grants)):
        return invoke(repo.get_version,identifier,number,permissions=permissions)

    @router.post('/{identifier}/versions/{number}/restore')
    def restore(req:Expected,identifier:int=Path(ge=1),number:int=Path(ge=1),user=Depends(require_logged_in_user),permissions=Depends(grants)):
        return invoke(repo.restore,identifier,number,req.expectedVersion,user['id'] if user else None,permissions=permissions)

    @router.get('/{identifier}/versions/{number}/export')
    def export(identifier:int=Path(ge=1),number:int=Path(ge=1),format:Literal['md','zip']='md',user=Depends(require_logged_in_user),permissions=Depends(grants)):
        content=invoke(repo.download,identifier,number,format,user['id'] if user else None,permissions=permissions)
        return Response(content,media_type='text/markdown; charset=utf-8' if format=='md' else 'application/zip',
                        headers={'Content-Disposition':f'attachment; filename="dc-{identifier}-v{number}.{format}"','Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
    @router.get('/{identifier}/versions/{number}/assets/{filename}')
    def asset(filename:str=Path(pattern=r'^[a-zA-Z0-9_-]+\.(png|svg)$',max_length=160),identifier:int=Path(ge=1),number:int=Path(ge=1),user=Depends(require_logged_in_user),permissions=Depends(grants)):
        content=invoke(repo.asset,identifier,number,filename,user['id'] if user else None,permissions=permissions)
        return Response(content,media_type='image/png' if filename.endswith('.png') else 'image/svg+xml',
                        headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; style-src 'none'; sandbox"})
    return router
