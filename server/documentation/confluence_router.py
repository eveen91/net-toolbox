"""Phase 3 endpoints: local configuration and preview, remote GET only."""
from fastapi import APIRouter,Depends,Path,Query,HTTPException
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from . import confluence_profiles as profiles,confluence_preview as previews
from .confluence_client import RemoteError
from .confluence_schema import ConnectionProfile,UpdateConnection,ConnectionExpected,ConfluencePreviewRequest,PublishRequest,JobExpected,JobControl,JobRevalidate,JobResolve
from . import confluence_publish as publication,confluence_jobs as jobs


class PrivateValidationRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def handle(request):
            try:return await original(request)
            except RequestValidationError as exc:
                # FastAPI's default validation response can echo submitted tokens
                # or a PEM private key. Return field locations/messages only.
                return JSONResponse(status_code=422,content={'detail':[{key:item[key] for key in ('loc','msg','type')} for item in exc.errors()]})
        return handle


def build_router(grants,require_logged_in_user,invoke):
    router=APIRouter(prefix='/confluence',route_class=PrivateValidationRoute)
    def run(operation,*args,permissions):
        try:return invoke(operation,*args,permissions=permissions)
        except RemoteError as exc:raise HTTPException(502,{'code':exc.code,'message':exc.message}) from None

    @router.get('/profiles')
    def listing(permissions=Depends(grants)):return run(profiles.listing,permissions=permissions)

    @router.get('/profiles/{identifier}')
    def detail(identifier:int=Path(ge=1),permissions=Depends(grants)):return run(profiles.detail,identifier,permissions=permissions)

    @router.post('/profiles',status_code=201)
    def create(req:ConnectionProfile,user=Depends(require_logged_in_user),permissions=Depends(grants)):
        return run(profiles.save,req,user['id'] if user else None,permissions=permissions)

    @router.put('/profiles/{identifier}')
    def update(req:UpdateConnection,identifier:int=Path(ge=1),user=Depends(require_logged_in_user),permissions=Depends(grants)):
        return run(profiles.save,req,user['id'] if user else None,identifier,permissions=permissions)

    @router.post('/profiles/{identifier}/check')
    def check(req:ConnectionExpected,identifier:int=Path(ge=1),user=Depends(require_logged_in_user),permissions=Depends(grants)):
        return run(previews.check,identifier,req.expectedVersion,user['id'] if user else None,permissions=permissions)

    @router.post('/documents/{identifier}/versions/{number}/previews',status_code=201)
    def prepare(req:ConfluencePreviewRequest,identifier:int=Path(ge=1),number:int=Path(ge=1),user=Depends(require_logged_in_user),permissions=Depends(grants)):
        return run(previews.prepare,identifier,number,req.profileId,req.expectedVersion,user['id'] if user else None,permissions=permissions)

    @router.get('/documents/{identifier}/versions/{number}/previews')
    def history(identifier:int=Path(ge=1),number:int=Path(ge=1),limit:int=Query(20,ge=1,le=50),offset:int=Query(0,ge=0),permissions=Depends(grants)):
        return run(previews.listing,identifier,number,limit,offset,permissions=permissions)

    @router.get('/documents/{identifier}/versions/{number}/previews/{preview_id}')
    def preview(preview_id:str=Path(pattern=r'^[a-f0-9-]{36}$'),identifier:int=Path(ge=1),number:int=Path(ge=1),permissions=Depends(grants)):
        return run(previews.get,preview_id,identifier,number,permissions=permissions)
    @router.post('/documents/{identifier}/versions/{number}/jobs',status_code=201)
    def publish(req:PublishRequest,identifier:int=Path(ge=1),number:int=Path(ge=1),user=Depends(require_logged_in_user),permissions=Depends(grants)):
        return run(publication.start,identifier,number,req,user['id'] if user else None,permissions=permissions)

    @router.get('/documents/{identifier}/versions/{number}/jobs')
    def publications(identifier:int=Path(ge=1),number:int=Path(ge=1),limit:int=Query(20,ge=1,le=50),offset:int=Query(0,ge=0),permissions=Depends(grants)):
        return run(jobs.listing,identifier,number,limit,offset,permissions=permissions)

    @router.get('/documents/{identifier}/versions/{number}/jobs/{job_id}')
    def job(job_id:str=Path(pattern=r'^[a-f0-9-]{36}$'),identifier:int=Path(ge=1),number:int=Path(ge=1),limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),permissions=Depends(grants)):
        return run(jobs.get,job_id,identifier,number,limit,offset,permissions=permissions)

    @router.post('/documents/{identifier}/versions/{number}/jobs/{job_id}/advance')
    def advance(req:JobExpected,job_id:str=Path(pattern=r'^[a-f0-9-]{36}$'),identifier:int=Path(ge=1),number:int=Path(ge=1),user=Depends(require_logged_in_user),permissions=Depends(grants)):
        return run(publication.advance,job_id,identifier,number,req.expectedRevision,user['id'] if user else None,permissions=permissions)

    @router.post('/documents/{identifier}/versions/{number}/jobs/{job_id}/control')
    def control(req:JobControl,job_id:str=Path(pattern=r'^[a-f0-9-]{36}$'),identifier:int=Path(ge=1),number:int=Path(ge=1),user=Depends(require_logged_in_user),permissions=Depends(grants)):
        return run(jobs.control,job_id,identifier,number,req.expectedRevision,req.action,user['id'] if user else None,permissions=permissions)
    @router.post('/documents/{identifier}/versions/{number}/jobs/{job_id}/revalidate')
    def revalidate(req:JobRevalidate,job_id:str=Path(pattern=r'^[a-f0-9-]{36}$'),identifier:int=Path(ge=1),number:int=Path(ge=1),user=Depends(require_logged_in_user),permissions=Depends(grants)):
        return run(publication.revalidate,job_id,identifier,number,req.expectedRevision,req.expectedProfileVersion,user['id'] if user else None,permissions=permissions)

    @router.post('/documents/{identifier}/versions/{number}/jobs/{job_id}/resolve')
    def resolve(req:JobResolve,job_id:str=Path(pattern=r'^[a-f0-9-]{36}$'),identifier:int=Path(ge=1),number:int=Path(ge=1),user=Depends(require_logged_in_user),permissions=Depends(grants)):
        return run(publication.resolve,job_id,identifier,number,req,user['id'] if user else None,permissions=permissions)
    return router
