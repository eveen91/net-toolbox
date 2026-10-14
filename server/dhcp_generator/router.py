import sqlite3
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from . import repository, service
from .schemas import Create, Save, Publish, Restore, Revision
from .vendor.generator import ConfigurationError


def invoke(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except repository.Missing:
        raise HTTPException(404, 'DHCP configuration or version not found')
    except repository.Conflict as exc:
        raise HTTPException(409, exc.detail)
    except ConfigurationError as exc:
        raise HTTPException(422, {'code': 'invalid_configuration', 'message': str(exc)})
    except repository.Invalid as exc:
        raise HTTPException(400, str(exc))
    except service.CheckFailed as exc:
        raise HTTPException(422 if exc.report['syntax_status'] == 'syntax_error' else 503,
                            {'code': exc.report['syntax_status'], 'message': 'Generated configuration could not pass the configured syntax check', 'report': exc.report})
    except sqlite3.OperationalError:
        raise HTTPException(503, 'DHCP storage is busy or unavailable. Retry shortly')
    except ValueError:
        raise HTTPException(503, 'DHCP syntax parser configuration is invalid')


def build_router(require_feature, require_logged_in_user):
    router = APIRouter(prefix='/api/dhcp-generator/configurations', tags=['dhcp-generator'],
                       dependencies=[Depends(require_feature('dhcp-generator'))])

    @router.get('')
    def listing(query: str = Query(default='', max_length=100), limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0)):
        return invoke(repository.listing, query.strip(), limit, offset)

    @router.post('', status_code=201)
    def create(req: Create, user=Depends(require_logged_in_user)):
        return invoke(repository.create, req.configuration.model_dump(exclude_none=True), user)

    @router.get('/{configuration_id}')
    def detail(configuration_id: int = Path(ge=1)):
        return invoke(repository.get_configuration, configuration_id)

    @router.put('/{configuration_id}')
    def save(req: Save, configuration_id: int = Path(ge=1), user=Depends(require_logged_in_user)):
        return invoke(repository.save, configuration_id, req.expectedRevision, req.configuration.model_dump(exclude_none=True), user)

    @router.post('/{configuration_id}/preview')
    def preview(req: Revision, configuration_id: int = Path(ge=1)):
        return invoke(service.preview, configuration_id, req.expectedRevision)

    @router.post('/{configuration_id}/versions', status_code=201)
    def publish(req: Publish, configuration_id: int = Path(ge=1), user=Depends(require_logged_in_user)):
        return invoke(service.publish, configuration_id, req.expectedRevision, req.description, user)

    @router.get('/{configuration_id}/versions')
    def versions(configuration_id: int = Path(ge=1), limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0)):
        return invoke(repository.versions, configuration_id, limit, offset)

    @router.get('/{configuration_id}/versions/{version_id}')
    def version(configuration_id: int = Path(ge=1), version_id: UUID = Path()):
        return invoke(repository.get_version, configuration_id, str(version_id))

    @router.get('/{configuration_id}/versions/{version_id}/artifact')
    def artifact(configuration_id: int = Path(ge=1), version_id: UUID = Path()):
        metadata, content = invoke(repository.artifact, configuration_id, str(version_id))
        name = metadata['configuration']['firewall']
        return Response(content, media_type='text/plain', headers={'Content-Disposition': f'attachment; filename="{name}-v{metadata["number"]}-dhcpd.conf"',
                                                                  'ETag': f'"{metadata["sha256"]}"', 'Cache-Control': 'private, no-store'})

    @router.post('/{configuration_id}/restore')
    def restore(req: Restore, configuration_id: int = Path(ge=1), user=Depends(require_logged_in_user)):
        return invoke(repository.save, configuration_id, req.expectedRevision, None, user, source_version=req.versionId)

    @router.get('/{configuration_id}/diff')
    def compare(configuration_id: int = Path(ge=1), before: UUID = Query(), after: UUID = Query()):
        return invoke(service.compare, configuration_id, str(before), str(after))

    @router.get('/{configuration_id}/audit')
    def history(configuration_id: int = Path(ge=1), limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0)):
        return invoke(repository.history, configuration_id, limit, offset)

    return router
