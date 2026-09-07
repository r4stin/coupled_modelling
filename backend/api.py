"""HTTP layer of the knowledge base: FastAPI routes under /api/v1.0/ over the
framework-agnostic core in main.py. The web explorer lives in the separate
coupled-modelling-frontend repository."""
import functools
import os
import threading
import traceback

import uvicorn
from fastapi import APIRouter, FastAPI, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from main import (
    REPOSITORY,
    SEARCH_RESULT_LIMIT,
    GraphDBError,
    add_values_sparql,
    copy_instance,
    copy_instance_recursively,
    create_class_instance_sparql,
    create_coupled,
    create_instance_sparql,
    delete_instance_sparql,
    delete_value_sparql,
    delete_values_sparql,
    export_coupled_kratos,
    get_class_hierarchy,
    get_class_hierarchy_metadata,
    get_class_instance_summaries,
    get_class_instances,
    get_class_metadata,
    get_class_properties_recursively,
    get_graphdb_health,
    get_instance_deletion_preview,
    get_instance_properties_recursively,
    get_instance_property_metadata,
    get_onto_path,
    get_value_deletion_preview,
    import_coupled_kratos,
    infer_coupled_system_structure,
    reload_ontology_from_graphdb,
    replace_properties_sparql,
    replace_value_sparql,
    replace_values_sparql,
    save_locally,
    save_onto,
    search_entities,
)
from schemas import (
    CopyInstanceBody,
    CopyInstanceRecursivelyBody,
    CoupledSystemBody,
    CreateClassInstanceBody,
    CreateCoupledBody,
    CreateInstanceBody,
    DeleteInstanceBody,
    DeleteValueBody,
    DeleteValuesBody,
    ImportKratosBody,
    InstanceDataBody,
    ReplaceValueBody,
)

API_PREFIX = '/api/v1.0'
SPEC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'openapi.yaml')

# Comma-separated list of allowed origins; defaults to the local frontend dev server.
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:3000').split(',')
    if origin.strip()
]


def error_response(status, message):
    return JSONResponse(status_code=status, content={'error': message})


async def error_floor(request, call_next):
    """Floor for failures no route mapping caught: the error shape, never a plain-text 500."""
    try:
        return await call_next(request)
    except Exception as exc:
        traceback.print_exc()
        return error_response(500, str(exc))


# openapi.yaml is the published contract; the generated document stays unpublished.
app = FastAPI(title='Coupled Modelling API', version='1.0.0', openapi_url=None, docs_url=None, redoc_url=None)
# The floor sits inside the CORS layer so its responses carry the CORS headers too.
app.middleware('http')(error_floor)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_methods=['GET', 'POST', 'OPTIONS'],
    allow_headers=['Content-Type'],
    max_age=86400,
)
router = APIRouter(prefix=API_PREFIX)


def get_route(path, **kwargs):
    """GET route that also answers HEAD, as the previous framework did."""
    return router.api_route(path, methods=['GET', 'HEAD'], **kwargs)


# The Owlready2 routes rebind the module-level ontology; one at a time.
SEMANTIC_LOCK = threading.Lock()

# Failure class -> status, checked in order.
EXPLORER_ERRORS = ((GraphDBError, 503), (ValueError, 400), (Exception, 500))
LEGACY_ERRORS = ((Exception, 400),)
DOWNLOAD_ERRORS = ((Exception, 500),)


def describe_validation(exc):
    parts = []
    for error in exc.errors():
        # Integer parts are list indexes or byte offsets, not parameter names.
        location = [part for part in error.get('loc', ()) if isinstance(part, str) and part not in ('body', 'query')]
        parts.append(f"{'.'.join(location) or 'request'}: {error.get('msg')}")
    return '; '.join(parts)


@app.exception_handler(RequestValidationError)
def validation_error(request, exc):
    return error_response(400, describe_validation(exc))


@app.exception_handler(StarletteHTTPException)
def http_error(request, exc):
    return error_response(exc.status_code, str(exc.detail))


def mapped(errors):
    """Turns the failure classes of a route into the documented error responses."""
    def decorate(endpoint):
        @functools.wraps(endpoint)
        def wrapper(*args, **kwargs):
            try:
                return endpoint(*args, **kwargs)
            except Exception as exc:
                for failure, status in errors:
                    if isinstance(exc, failure):
                        if status >= 500:
                            traceback.print_exc()
                        return error_response(status, str(exc))
                raise
        return wrapper
    return decorate


def health_error(status, exc):
    return JSONResponse(
        status_code=status,
        content={'status': 'error', 'graphdb': 'unavailable', 'repository': REPOSITORY, 'error': str(exc)},
    )


@get_route('/openapi.yaml')
def api_openapi_spec():
    return FileResponse(SPEC_PATH, media_type='application/yaml')


@get_route('/docs', include_in_schema=False)
def api_docs():
    return get_swagger_ui_html(openapi_url=f'{API_PREFIX}/openapi.yaml', title='Coupled Modelling API')


def ontology_bytes():
    """Serialises the current ontology to disk and returns the bytes while the lock is still held."""
    save_locally()
    with open(get_onto_path(), 'rb') as ontology_file:
        return ontology_file.read()


@get_route('/health/')
def api_health():
    try:
        return get_graphdb_health()
    except GraphDBError as exc:
        return health_error(503, exc)
    except Exception as exc:
        return health_error(500, exc)


@get_route('/get_class_hierarchy_metadata/')
@mapped(EXPLORER_ERRORS)
def api_get_class_hierarchy_metadata():
    return get_class_hierarchy_metadata()


@get_route('/get_class_instance_summaries/')
@mapped(EXPLORER_ERRORS)
def api_get_class_instance_summaries(class_name: str | None = Query(None, alias='class')):
    return get_class_instance_summaries(class_name)


@get_route('/search/')
@mapped(EXPLORER_ERRORS)
def api_search(q: str | None = None, entity_type: str = Query('all', alias='type'), limit: str | None = None):
    try:
        limit_value = int(limit) if limit else SEARCH_RESULT_LIMIT
    except ValueError:
        return error_response(400, 'limit must be an integer')
    return search_entities(q, entity_type, limit_value)


@get_route('/get_class_metadata/')
@mapped(EXPLORER_ERRORS)
def api_get_class_metadata(class_name: str | None = Query(None, alias='class')):
    if not class_name:
        return error_response(400, 'Missing required query parameter: class')
    return get_class_metadata(class_name)


@get_route('/get_instance_property_metadata/')
@mapped(EXPLORER_ERRORS)
def api_get_instance_property_metadata(instance: str | None = None):
    if not instance:
        return error_response(400, 'Missing required query parameter: instance')
    return get_instance_property_metadata(instance)


@router.post('/import_coupled_kratos/', status_code=201)
@mapped(LEGACY_ERRORS)
def api_import_coupled_kratos(body: ImportKratosBody):
    try:
        with SEMANTIC_LOCK:
            reload_ontology_from_graphdb()
            inst = import_coupled_kratos(body.data, body.label)
            save_onto()
    except Exception:
        traceback.print_exc()
        raise
    return inst


@router.post('/create_coupled/', status_code=201)
@mapped(LEGACY_ERRORS)
def api_create_coupled(body: CreateCoupledBody):
    with SEMANTIC_LOCK:
        reload_ontology_from_graphdb()
        inst = create_coupled(body.label)
        save_onto()
    return inst


@router.post('/copy_instance_recursively/', status_code=201)
@mapped(LEGACY_ERRORS)
def api_copy_instance_recursively(body: CopyInstanceRecursivelyBody):
    with SEMANTIC_LOCK:
        reload_ontology_from_graphdb()
        inst = copy_instance_recursively(body.instance, body.parent, body.data, body.depth, body.recursive)
        save_onto()
    return inst


@router.post('/copy_instance/', status_code=201)
@mapped(LEGACY_ERRORS)
def api_copy_instance(body: CopyInstanceBody):
    with SEMANTIC_LOCK:
        reload_ontology_from_graphdb()
        new_inst = copy_instance(body.instance, body.parent, body.data)
        save_onto()
    return new_inst


@router.post('/create_instance/', status_code=201)
@mapped(EXPLORER_ERRORS)
def api_create_instance(body: CreateInstanceBody):
    return create_instance_sparql(body.property, body.parent, body.data)


@get_route('/get_instance_properties_recursively/')
@mapped(LEGACY_ERRORS)
def api_get_instance_properties_recursively(instance: str | None = None, depth: int | None = None, recursive: bool = False):
    with SEMANTIC_LOCK:
        reload_ontology_from_graphdb()
        return get_instance_properties_recursively(instance, depth, recursive)


@router.post('/replace_values/', status_code=201)
@mapped(EXPLORER_ERRORS)
def api_replace_values(body: InstanceDataBody):
    replace_values_sparql(body.instance, body.data)
    return ''


@router.post('/delete_values/', status_code=201)
@mapped(EXPLORER_ERRORS)
def api_delete_values(body: DeleteValuesBody):
    delete_values_sparql(body.instance, body.properties)
    return ''


@router.post('/add_values/', status_code=201)
@mapped(EXPLORER_ERRORS)
def api_add_values(body: InstanceDataBody):
    add_values_sparql(body.instance, body.data)
    return ''


@router.post('/replace_properties/', status_code=201)
@mapped(EXPLORER_ERRORS)
def api_replace_properties(body: InstanceDataBody):
    replace_properties_sparql(body.instance, body.data)
    return ''


@router.post('/infer_coupled_structure/', status_code=201)
@mapped(LEGACY_ERRORS)
def api_infer_coupled_structure(body: CoupledSystemBody):
    with SEMANTIC_LOCK:
        reload_ontology_from_graphdb()
        infer_coupled_system_structure(body.coupled_system)
        save_onto()
    return ''


@router.post('/export_coupled_kratos/', status_code=201)
@mapped(LEGACY_ERRORS)
def api_export_coupled_kratos(body: CoupledSystemBody):
    with SEMANTIC_LOCK:
        reload_ontology_from_graphdb()
        return export_coupled_kratos(body.coupled_system)


@router.post('/save_onto/', status_code=201)
@mapped(LEGACY_ERRORS)
def api_save_onto():
    with SEMANTIC_LOCK:
        save_onto()
    return ''


@get_route('/save_locally/')
@mapped(LEGACY_ERRORS)
def api_save_locally():
    with SEMANTIC_LOCK:
        reload_ontology_from_graphdb()
        data = ontology_bytes()
    return Response(content=data, media_type='application/rdf+xml', headers={'Content-Disposition': 'inline; filename="onto.owl"'})


@get_route('/get_class_hierarchy/')
@mapped(LEGACY_ERRORS)
def api_get_class_hierarchy():
    return get_class_hierarchy()


@get_route('/get_class_properties_recursively/')
@mapped(LEGACY_ERRORS)
def api_get_class_properties_recursively(class_name: str | None = Query(None, alias='class'), depth: int | None = None, recursive: bool = False):
    with SEMANTIC_LOCK:
        reload_ontology_from_graphdb()
        return get_class_properties_recursively(class_name, depth, recursive)


@get_route('/get_class_instances/')
@mapped(LEGACY_ERRORS)
def api_get_class_instances(class_name: str | None = Query(None, alias='class')):
    return get_class_instances(class_name)


@router.post('/replace_value/', status_code=201)
@mapped(EXPLORER_ERRORS)
def api_replace_value(body: ReplaceValueBody | None = None):
    body = body or ReplaceValueBody()
    if not body.instance or not body.property or body.old_value is None or body.new_value is None:
        return error_response(400, 'instance, property, old_value, and new_value parameters are required')
    replace_value_sparql(body.instance, body.property, body.old_value, body.new_value)
    return ''


@router.post('/delete_value/')
@mapped(EXPLORER_ERRORS)
def api_delete_value(body: DeleteValueBody | None = None):
    body = body or DeleteValueBody()
    if not body.instance or not body.property or body.value is None:
        return error_response(400, 'instance, property, and value parameters are required')
    result = delete_value_sparql(body.instance, body.property, body.value, cascade=body.cascade)
    return {'status': 'success', **result}


@get_route('/get_value_deletion_preview/')
@mapped(EXPLORER_ERRORS)
def api_get_value_deletion_preview(instance: str | None = None, property: str | None = None, target: str | None = None):
    if not instance or not property or not target:
        return error_response(400, 'Missing required query parameters: instance, property, target')
    return get_value_deletion_preview(instance, property, target)


@router.post('/create_class_instance/', status_code=201)
@mapped(EXPLORER_ERRORS)
def api_create_class_instance(body: CreateClassInstanceBody | None = None):
    body = body or CreateClassInstanceBody()
    if not body.class_name or not body.label:
        return error_response(400, 'class and label parameters are required')
    return create_class_instance_sparql(body.class_name, body.label)


@router.post('/delete_instance/')
@mapped(EXPLORER_ERRORS)
def api_delete_instance(body: DeleteInstanceBody | None = None):
    body = body or DeleteInstanceBody()
    if not body.instance:
        return error_response(400, 'instance parameter is required')
    result = delete_instance_sparql(body.instance, cascade=body.cascade)
    return {'status': 'success', **result}


@get_route('/get_instance_deletion_preview/')
@mapped(EXPLORER_ERRORS)
def api_get_instance_deletion_preview(instance: str | None = None, cascade: bool = True):
    if not instance:
        return error_response(400, 'Missing required query parameter: instance')
    return get_instance_deletion_preview(instance, cascade=cascade)


@get_route('/download_owl/')
@mapped(DOWNLOAD_ERRORS)
def api_download_owl():
    with SEMANTIC_LOCK:
        reload_ontology_from_graphdb()
        data = ontology_bytes()
    return Response(content=data, media_type='application/rdf+xml', headers={'Content-Disposition': 'attachment; filename="onto.owl"'})


app.include_router(router)


if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=5000)
