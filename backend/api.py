"""HTTP layer of the knowledge base: FastAPI routes under /api/v1.0/ over the
framework-agnostic core in main.py. The OpenAPI document is generated from
these routes and served as YAML at /api/v1.0/openapi.yaml. The web explorer
lives in the separate coupled-modelling-frontend repository."""
import functools
import os
import re
import threading
import traceback
from typing import Literal

import uvicorn
import yaml
from fastapi import APIRouter, FastAPI, Query
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic.json_schema import SkipJsonSchema
from starlette.exceptions import HTTPException as StarletteHTTPException

from main import (
    REPOSITORY,
    SEARCH_RESULT_LIMIT,
    SEARCH_RESULT_LIMIT_MAX,
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
    ClassAxiom,
    ClassHierarchyEntry,
    ClassMetadata,
    CopyInstanceBody,
    CopyInstanceRecursivelyBody,
    CoupledSystemBody,
    CreateClassInstanceBody,
    CreateCoupledBody,
    CreateInstanceBody,
    DeleteInstanceBody,
    DeleteValueBody,
    DeleteValuesBody,
    DeletionPreview,
    EMPTY_BODY_DESCRIPTION,
    EmptyBody,
    Error,
    HealthError,
    HealthOk,
    ImportKratosBody,
    InstanceDataBody,
    InstanceDeletionResult,
    InstanceId,
    InstanceMetadata,
    InstanceSummary,
    KratosParameters,
    NestedProperties,
    ReplaceValueBody,
    SearchResults,
    UnlinkResult,
    ValueDeletionResult,
    target_payload,
)

API_PREFIX = '/api/v1.0'
API_TITLE = 'Coupled Modelling API'
API_VERSION = '1.0.0'
API_SUMMARY = 'REST API for the coupled multiphysics simulation knowledge base.'
API_DESCRIPTION = """HTTP API of the coupled_modelling backend: a knowledge base that stores
Kratos CoSimulation configurations as OWL/RDF in a GraphDB triple store.

The backend uses a hybrid architecture:

* **Direct SPARQL path** — reads and simple mutations (adding, replacing and
  deleting property values, creating and deleting instances) are executed as
  stateless SPARQL queries/updates directly against GraphDB.
* **In-memory semantic path** — structurally complex workflows (Kratos JSON
  import/export, recursive instance copying, class-axiom inference) load the
  ontology into Owlready2, operate on it in memory and synchronise the
  result back to GraphDB.

Instances created through the API receive collision-resistant UUID
identifiers (for example `instance_550e8400-e29b-41d4-a716-446655440000`);
human-readable names are stored separately as `rdfs:label` annotations.
"""
API_TAGS = [
    {'name': 'system', 'description': 'Health and connection status.'},
    {'name': 'explorer', 'description': 'Read-only metadata endpoints backing the web explorer (direct SPARQL).'},
    {'name': 'mutations', 'description': 'Stateless create/update/delete operations executed as direct SPARQL updates.'},
    {'name': 'semantic', 'description': 'Owlready2 in-memory workflows (Kratos import/export, copying, inference).'},
    {'name': 'files', 'description': 'Ontology file downloads and persistence.'},
    {'name': 'legacy', 'description': 'Early read endpoints kept for compatibility; the explorer endpoints supersede them.'},
]

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


app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
    summary=API_SUMMARY,
    description=API_DESCRIPTION,
    openapi_tags=API_TAGS,
    servers=[{'url': 'http://localhost:5000', 'description': 'Local development server (uvicorn)'}],
    contact={'name': 'coupled_modelling repository', 'url': 'https://github.com/ldrbmrtv/coupled_modelling'},
    openapi_url=f'{API_PREFIX}/openapi.json',
    docs_url=f'{API_PREFIX}/docs',
    redoc_url=None,
    swagger_ui_oauth2_redirect_url=None,
)
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
    """GET route that also answers HEAD (undocumented), as the previous framework did."""
    def decorate(endpoint):
        router.add_api_route(path, endpoint, methods=['GET'], **kwargs)
        router.add_api_route(path, endpoint, methods=['HEAD'], include_in_schema=False)
        return endpoint
    return decorate


def generate_openapi():
    """The published contract: FastAPI's document without the 422 responses the app never emits."""
    # FastAPI caches the dict it returns, so stripping it once in place strips every later call too.
    cached = app.openapi_schema is not None
    schema = FastAPI.openapi(app)
    if not cached:
        for path_item in schema['paths'].values():
            for operation in path_item.values():
                operation.get('responses', {}).pop('422', None)
        for name in ('HTTPValidationError', 'ValidationError'):
            schema.get('components', {}).get('schemas', {}).pop(name, None)
    return schema


app.openapi = generate_openapi


def openapi_yaml():
    """The contract as YAML, rendered once per process (the served file and the committed file share it)."""
    if not hasattr(app.state, 'openapi_yaml'):
        dumper = getattr(yaml, 'CSafeDumper', yaml.SafeDumper)
        app.state.openapi_yaml = yaml.dump(app.openapi(), Dumper=dumper, sort_keys=False, allow_unicode=True)
    return app.state.openapi_yaml


class YamlResponse(Response):
    media_type = 'application/yaml'


class RdfXmlResponse(Response):
    media_type = 'application/rdf+xml'


# The Owlready2 routes rebind the module-level ontology; one at a time.
SEMANTIC_LOCK = threading.Lock()

# Failure class -> status, checked in order.
EXPLORER_ERRORS = ((GraphDBError, 503), (ValueError, 400), (Exception, 500))
LEGACY_ERRORS = ((Exception, 400),)
DOWNLOAD_ERRORS = ((Exception, 500),)

BAD_REQUEST = {'model': Error, 'description': 'Invalid input (missing parameters, unknown subject/class, or validation failure).'}
GRAPHDB_UNAVAILABLE = {'model': Error, 'description': 'GraphDB is unreachable or the repository is offline.'}
UNEXPECTED_ERROR = {'model': Error, 'description': 'Unexpected server error.'}
EXPLORER_RESPONSES = {400: BAD_REQUEST, 503: GRAPHDB_UNAVAILABLE, 500: UNEXPECTED_ERROR}
LEGACY_RESPONSES = {400: BAD_REQUEST}
DOWNLOAD_RESPONSES = {500: UNEXPECTED_ERROR}


def json_error(response):
    """An error response documented as JSON on a route whose success body is not JSON."""
    return {'description': response['description'], 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/Error'}}}}


FILE_LEGACY_RESPONSES = {400: json_error(BAD_REQUEST)}
FILE_DOWNLOAD_RESPONSES = {500: json_error(UNEXPECTED_ERROR)}


# Location parts pydantic adds for union branches, discriminator values and type tags; only field names are kept.
TYPE_TAG = re.compile(r'^(tagged-union|union|literal|object|nullable|function-[a-z]+|json-or-python|lax-or-strict|str|int|float|bool|dict|list|none)(\[.*\])?$')


def required_body_fields(request):
    """Aliases of the required fields of the route's body model, for an absent-body message."""
    body_field = getattr(request.scope.get('route'), 'body_field', None)
    model = getattr(getattr(body_field, 'field_info', None), 'annotation', None)
    fields = getattr(model, 'model_fields', {})
    return [field.alias or name for name, field in fields.items() if field.is_required()]


def describe_validation(exc, request=None):
    """One line per offending field: the first message of a union, without pydantic's branch tags."""
    messages = {}
    for error in exc.errors():
        loc = error.get('loc', ())
        if tuple(loc) == ('body',) and error.get('type') == 'missing' and request is not None:
            names = required_body_fields(request)
            messages.setdefault(', '.join(names) or 'request', error.get('msg'))
            continue
        # Integer parts are list indexes or byte offsets, not parameter names.
        location = [part for part in loc if isinstance(part, str) and part not in ('body', 'query', 'response') and not TYPE_TAG.match(part)]
        messages.setdefault('.'.join(location) or 'request', error.get('msg'))
    return '; '.join(f'{field}: {message}' for field, message in messages.items())


@app.exception_handler(RequestValidationError)
def validation_error(request, exc):
    return error_response(400, describe_validation(exc, request))


@app.exception_handler(ResponseValidationError)
def response_contract_error(request, exc):
    """A core result outside the contract: a 500 in the error shape, the details in the log only."""
    traceback.print_exc()
    return error_response(500, f'Response does not match the API contract: {describe_validation(exc)}')


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


# --- system ---


@get_route(
    '/openapi.yaml',
    tags=['system'],
    operation_id='getOpenApiSpec',
    summary='Download this OpenAPI specification',
    response_class=YamlResponse,
    response_description='The OpenAPI 3.1 specification in YAML.',
)
def api_openapi_spec():
    """Serves the OpenAPI document generated from the running backend, so clients and tooling can generate typed bindings without a copy of the repository."""
    return YamlResponse(openapi_yaml())


@get_route(
    '/health/',
    tags=['system'],
    operation_id='getHealth',
    summary='Check GraphDB connectivity',
    response_model=HealthOk,
    response_description='GraphDB is reachable and the repository responds.',
    responses={
        503: {**GRAPHDB_UNAVAILABLE, 'model': HealthError},
        500: {'model': HealthError, 'description': 'Unexpected server error during the health check.'},
    },
)
def api_health():
    """Verifies that the configured GraphDB repository answers a trivial `ASK` query."""
    try:
        return get_graphdb_health()
    except GraphDBError as exc:
        return health_error(503, exc)
    except Exception as exc:
        return health_error(500, exc)


# --- explorer ---


@get_route(
    '/get_class_hierarchy_metadata/',
    tags=['explorer'],
    operation_id='getClassHierarchyMetadata',
    summary='List all ontology classes with their direct parents',
    response_model=list[ClassHierarchyEntry],
    response_description='Alphabetically sorted class list.',
    responses=EXPLORER_RESPONSES,
)
@mapped(EXPLORER_ERRORS)
def api_get_class_hierarchy_metadata():
    """Returns every project-local OWL class together with the list of its direct named superclasses.
    The frontend builds the class tree from the parent arrays (classes with an empty `parents` array are roots)."""
    return get_class_hierarchy_metadata()


@get_route(
    '/search/',
    tags=['explorer'],
    operation_id='searchEntities',
    summary='Search classes and instances by name or label',
    response_model=SearchResults,
    response_description='Matching classes and instances.',
    responses={**EXPLORER_RESPONSES, 400: {'model': Error, 'description': 'Missing or empty `q`, unknown `type`, or `limit` out of range.'}},
)
@mapped(EXPLORER_ERRORS)
def api_search(
    q: str = Query(description='Search text (matched as a case-insensitive substring).', examples=['mok']),
    entity_type: Literal['all', 'class', 'instance'] = Query('all', alias='type', description='Restrict results to one entity kind.'),
    limit: int = Query(SEARCH_RESULT_LIMIT, ge=1, le=SEARCH_RESULT_LIMIT_MAX, description='Maximum results per group (1-100).'),
):
    """Case-insensitive substring search over the local names and labels of project classes and instances.
    Each result group is capped at `limit`; matches on a name prefix rank before other matches.
    Instance results carry the same summary shape as `get_class_instance_summaries`."""
    return search_entities(q, entity_type, limit)


@get_route(
    '/get_class_instance_summaries/',
    tags=['explorer'],
    operation_id='getClassInstanceSummaries',
    summary='List instance summaries for a class',
    response_model=list[InstanceSummary],
    response_description='Instance summaries sorted by label.',
    responses={**EXPLORER_RESPONSES, 400: {'model': Error, 'description': 'The class does not exist in GraphDB.'}},
)
@mapped(EXPLORER_ERRORS)
def api_get_class_instance_summaries(
    class_name: str | SkipJsonSchema[None] = Query(None, alias='class', description='Local class name to list instances for (for example `solvers`). Omit for all instances.', examples=['solvers']),
):
    """Returns one summary per instance of the given class (including instances of its subclasses, via
    `rdf:type/rdfs:subClassOf*`). Each summary carries the resolved preferred label (English first, then
    untagged, then other languages), the direct types, and a compact preview of up to three property
    values for display under the instance title. When `class` is omitted, summaries for all instances are returned."""
    return get_class_instance_summaries(class_name)


@get_route(
    '/get_class_metadata/',
    tags=['explorer'],
    operation_id='getClassMetadata',
    summary='Get class descriptions, hierarchy links and restriction axioms',
    response_model=ClassMetadata,
    response_description='Class metadata.',
    responses={**EXPLORER_RESPONSES, 400: {'model': Error, 'description': 'Missing `class` parameter, or the class does not exist.'}},
)
@mapped(EXPLORER_ERRORS)
def api_get_class_metadata(class_name: str = Query(alias='class', description='Local class name (for example `coupled_system`).', examples=['coupled_system'])):
    """Returns metadata backing the class inspector pane: `rdfs:comment` / `skos:definition` descriptions,
    direct superclasses and subclasses, named equivalent classes, and the OWL restriction axioms asserted on
    the class (existential/universal/value restrictions and unqualified or qualified cardinality restrictions,
    including intersection targets expanded into their named member classes)."""
    return get_class_metadata(class_name)


@get_route(
    '/get_instance_property_metadata/',
    tags=['explorer'],
    operation_id='getInstancePropertyMetadata',
    summary="Get an instance's direct properties with type metadata",
    response_model=InstanceMetadata,
    response_description='Instance metadata for the inspector pane.',
    responses={
        **EXPLORER_RESPONSES,
        400: {'model': Error, 'description': 'Missing `instance` parameter, or the identifier is not an existing individual (classes and properties do not count).'},
    },
)
@mapped(EXPLORER_ERRORS)
def api_get_instance_property_metadata(
    instance: str = Query(description='Local instance identifier.', examples=['instance_550e8400-e29b-41d4-a716-446655440000']),
):
    """Returns the direct outgoing statements of an instance, grouped per property and sorted, with each value
    tagged as an `object` reference (id plus resolved label) or a typed `literal` (JSON-native value plus XSD
    datatype). Property names are returned without the `has_` prefix."""
    return get_instance_property_metadata(instance)


@get_route(
    '/get_value_deletion_preview/',
    tags=['explorer'],
    operation_id='getValueDeletionPreview',
    summary='Preview what removing an object link would delete',
    response_model=UnlinkResult,
    response_description='The unlink preview.',
    responses=EXPLORER_RESPONSES,
)
@mapped(EXPLORER_ERRORS)
def api_get_value_deletion_preview(
    instance: str = Query(description='Identifier of the instance holding the link.', examples=['instance_550e8400-e29b-41d4-a716-446655440000']),
    property: str = Query(description='Property name (without the `has_` prefix).', examples=['solver_settings']),
    target: str = Query(description='Identifier of the linked instance.'),
):
    """Read-only counterpart of `delete_value` for an object link: whether the linked instance would be deleted
    with its owned subtree (nothing else reaches it afterwards) or kept."""
    return get_value_deletion_preview(instance, property, target)


@get_route(
    '/get_instance_deletion_preview/',
    tags=['explorer'],
    operation_id='getInstanceDeletionPreview',
    summary='Preview what a cascading deletion of an instance would remove',
    response_model=DeletionPreview,
    response_description='The deletion preview.',
    responses=EXPLORER_RESPONSES,
)
@mapped(EXPLORER_ERRORS)
def api_get_instance_deletion_preview(
    instance: str = Query(description='Local instance identifier.', examples=['instance_550e8400-e29b-41d4-a716-446655440000']),
    cascade: bool = Query(True, description='Preview the cascading (default) or the single-instance deletion.'),
):
    """Read-only counterpart of `delete_instance`: the instances that would be deleted (the requested one first),
    the reachable ones that would be kept, and the surviving instances whose link would be removed."""
    return get_instance_deletion_preview(instance, cascade=cascade)


# --- mutations (direct SPARQL) ---


@router.post(
    '/create_instance/',
    tags=['mutations'],
    operation_id='createInstance',
    summary='Create an instance linked to a parent (direct SPARQL)',
    status_code=201,
    response_model=InstanceId,
    response_description='Identifier of the created instance.',
    responses=EXPLORER_RESPONSES,
)
@mapped(EXPLORER_ERRORS)
def api_create_instance(body: CreateInstanceBody):
    """Creates a new UUID-named instance of class `property`, links it to the existing `parent` instance via the
    corresponding `has_<property>` object property, and optionally asserts initial property values from `data`.
    String values that match the label of an existing instance of the property's class are resolved to object
    references; creating nested individuals inline is rejected."""
    return create_instance_sparql(body.property, body.parent, body.data)


@router.post(
    '/create_class_instance/',
    tags=['mutations'],
    operation_id='createClassInstance',
    summary='Create a standalone labelled instance (direct SPARQL)',
    status_code=201,
    response_model=InstanceId,
    response_description='Identifier of the created instance.',
    responses=EXPLORER_RESPONSES,
)
@mapped(EXPLORER_ERRORS)
def api_create_class_instance(body: CreateClassInstanceBody):
    """Creates a new UUID-named instance of the given class with an `rdfs:label`, without linking it to a parent."""
    return create_class_instance_sparql(body.class_name, body.label)


@router.post(
    '/add_values/',
    tags=['mutations'],
    operation_id='addValues',
    summary='Add property values to an instance (direct SPARQL)',
    status_code=201,
    response_model=EmptyBody,
    response_description=EMPTY_BODY_DESCRIPTION,
    responses=EXPLORER_RESPONSES,
)
@mapped(EXPLORER_ERRORS)
def api_add_values(body: InstanceDataBody):
    """Inserts the given property values for an existing instance in a single SPARQL update transaction. List
    values produce one triple per element. Plain string values are kept as literals for datatype properties; for
    object properties they are resolved to an existing instance of the property's class by label, or a new labeled
    instance is created when no match exists. Explicit `instance*` references must already exist."""
    add_values_sparql(body.instance, body.data)
    return ''


@router.post(
    '/replace_values/',
    tags=['mutations'],
    operation_id='replaceValues',
    summary='Replace property values on an instance (direct SPARQL)',
    status_code=201,
    response_model=EmptyBody,
    response_description=EMPTY_BODY_DESCRIPTION,
    responses=EXPLORER_RESPONSES,
)
@mapped(EXPLORER_ERRORS)
def api_replace_values(body: InstanceDataBody):
    """Replaces the existing values of each property in `data` with the given new values in a single SPARQL update
    transaction. An empty list (`[]`) removes all values of that property."""
    replace_values_sparql(body.instance, body.data)
    return ''


@router.post(
    '/replace_properties/',
    tags=['mutations'],
    operation_id='replaceProperties',
    summary="Replace an instance's property set (direct SPARQL)",
    status_code=201,
    response_model=EmptyBody,
    response_description=EMPTY_BODY_DESCRIPTION,
    responses=EXPLORER_RESPONSES,
)
@mapped(EXPLORER_ERRORS)
def api_replace_properties(body: InstanceDataBody):
    """Removes the instance's existing `has_*` and `rdfs:label` statements and asserts the given data instead,
    preserving structural metadata (`rdf:type`, `rdfs:comment`)."""
    replace_properties_sparql(body.instance, body.data)
    return ''


@router.post(
    '/replace_value/',
    tags=['mutations'],
    operation_id='replaceValue',
    summary='Atomically replace one specific property value (direct SPARQL)',
    status_code=201,
    response_model=EmptyBody,
    response_description=EMPTY_BODY_DESCRIPTION,
    responses=EXPLORER_RESPONSES,
)
@mapped(EXPLORER_ERRORS)
def api_replace_value(body: ReplaceValueBody):
    """Replaces one stored value with another in a single SPARQL update. The old value is matched by value equality
    (dangling references allowed); the new value keeps its exact datatype and language tag. When the old value no
    longer exists, the update is a no-op. Replacing an object value removes the old link only; the previous target
    is not garbage-collected."""
    replace_value_sparql(body.instance, body.property, target_payload(body.old_value), target_payload(body.new_value))
    return ''


@router.post(
    '/delete_value/',
    tags=['mutations'],
    operation_id='deleteValue',
    summary='Delete a single property value (direct SPARQL)',
    response_model=ValueDeletionResult,
    response_description='The value was deleted.',
    responses=EXPLORER_RESPONSES,
)
@mapped(EXPLORER_ERRORS)
def api_delete_value(body: DeleteValueBody):
    """Removes the triple. When the value is an object link and `cascade` is set (the default), the linked instance's
    owned subtree is deleted as well if nothing else reaches it afterwards: the same ownership rule as
    `delete_instance`. A coupled system, a target still linked from elsewhere, a link that is not stored, and the
    instance holding the link are never collected. The removal and the collection run in one transactional update.
    Use `get_value_deletion_preview` to see the outcome first."""
    result = delete_value_sparql(body.instance, body.property, target_payload(body.value), cascade=body.cascade)
    return {'status': 'success', **result}


@router.post(
    '/delete_values/',
    tags=['mutations'],
    operation_id='deleteValues',
    summary='Delete all values of the given properties (direct SPARQL)',
    status_code=201,
    response_model=EmptyBody,
    response_description=EMPTY_BODY_DESCRIPTION,
    responses=EXPLORER_RESPONSES,
)
@mapped(EXPLORER_ERRORS)
def api_delete_values(body: DeleteValuesBody):
    """Removes the triples only; unlinked instances are not garbage-collected."""
    delete_values_sparql(body.instance, body.properties)
    return ''


@router.post(
    '/delete_instance/',
    tags=['mutations'],
    operation_id='deleteInstance',
    summary='Delete an instance and, by default, its owned subtree (direct SPARQL)',
    response_model=InstanceDeletionResult,
    response_description='The instance was deleted.',
    responses=EXPLORER_RESPONSES,
)
@mapped(EXPLORER_ERRORS)
def api_delete_instance(body: DeleteInstanceBody):
    """Removes every outgoing and incoming triple of the instance in one transactional SPARQL update. With `cascade`
    (the default) the instance's owned subtree goes with it: every individual reachable through `has_*` links that
    is not reachable from outside the subtree. Coupled systems are never owned by another instance, so traversal
    stops at them. Individuals still reachable from elsewhere (an instance linked from outside and everything below
    it, shared vocabulary terms for example) are kept and reported in `kept`. With `cascade: false` only the instance
    itself is removed and its children are left in place. Use `get_instance_deletion_preview` to see the sets before
    deleting."""
    result = delete_instance_sparql(body.instance, cascade=body.cascade)
    return {'status': 'success', **result}


# --- semantic (Owlready2 in-memory path) ---


@router.post(
    '/import_coupled_kratos/',
    tags=['semantic'],
    operation_id='importCoupledKratos',
    summary='Import a Kratos CoSimulation JSON configuration',
    status_code=201,
    response_model=InstanceId,
    response_description='Identifier of the created coupled-system instance.',
    responses=LEGACY_RESPONSES,
)
@mapped(LEGACY_ERRORS)
def api_import_coupled_kratos(body: ImportKratosBody):
    """Recursively converts a Kratos CoSimulation parameters JSON object into OWL instances (CoSim2OWL), infers
    class-restriction axioms for the imported structure, and persists the updated ontology to GraphDB. Runs on
    the in-memory Owlready2 path."""
    try:
        with SEMANTIC_LOCK:
            reload_ontology_from_graphdb()
            inst = import_coupled_kratos(body.data, body.label)
            save_onto()
    except Exception:
        traceback.print_exc()
        raise
    return inst


@router.post(
    '/export_coupled_kratos/',
    tags=['semantic'],
    operation_id='exportCoupledKratos',
    summary='Export a coupled system as Kratos CoSimulation JSON',
    status_code=201,
    response_model=KratosParameters,
    response_description='The reconstructed Kratos parameters object.',
    responses=LEGACY_RESPONSES,
)
@mapped(LEGACY_ERRORS)
def api_export_coupled_kratos(body: CoupledSystemBody):
    """Reconstructs the nested Kratos CoSimulation parameters JSON for a stored coupled-system instance by
    recursively resolving its properties. Runs on the in-memory Owlready2 path."""
    with SEMANTIC_LOCK:
        reload_ontology_from_graphdb()
        return export_coupled_kratos(body.coupled_system)


@router.post(
    '/create_coupled/',
    tags=['semantic'],
    operation_id='createCoupled',
    summary='Create an empty coupled system',
    status_code=201,
    response_model=InstanceId,
    response_description='Identifier of the created coupled-system instance.',
    responses=LEGACY_RESPONSES,
)
@mapped(LEGACY_ERRORS)
def api_create_coupled(body: CreateCoupledBody):
    """Creates a new labelled instance of the `coupled_system` class and persists the ontology. Runs on the
    in-memory Owlready2 path."""
    with SEMANTIC_LOCK:
        reload_ontology_from_graphdb()
        inst = create_coupled(body.label)
        save_onto()
    return inst


@router.post(
    '/copy_instance/',
    tags=['semantic'],
    operation_id='copyInstance',
    summary='Copy an instance with its direct properties',
    status_code=201,
    response_model=InstanceId,
    response_description='Identifier of the created copy.',
    responses=LEGACY_RESPONSES,
)
@mapped(LEGACY_ERRORS)
def api_copy_instance(body: CopyInstanceBody):
    """Creates a structural copy of an instance, optionally attaching it to a parent via the appropriate inverse
    property and overriding selected property values with `data`. Runs on the in-memory Owlready2 path."""
    with SEMANTIC_LOCK:
        reload_ontology_from_graphdb()
        new_inst = copy_instance(body.instance, body.parent, body.data)
        save_onto()
    return new_inst


@router.post(
    '/copy_instance_recursively/',
    tags=['semantic'],
    operation_id='copyInstanceRecursively',
    summary='Copy an instance and its linked sub-structure',
    status_code=201,
    response_model=InstanceId,
    response_description='Identifier of the created copy.',
    responses=LEGACY_RESPONSES,
)
@mapped(LEGACY_ERRORS)
def api_copy_instance_recursively(body: CopyInstanceRecursivelyBody):
    """Like `copy_instance`, but also recursively copies linked child instances down to `depth` levels (or without
    limit when `recursive` is true). Runs on the in-memory Owlready2 path."""
    with SEMANTIC_LOCK:
        reload_ontology_from_graphdb()
        inst = copy_instance_recursively(body.instance, body.parent, body.data, body.depth, body.recursive)
        save_onto()
    return inst


@router.post(
    '/infer_coupled_structure/',
    tags=['semantic'],
    operation_id='inferCoupledStructure',
    summary='Infer class-restriction axioms for a coupled system',
    status_code=201,
    response_model=EmptyBody,
    response_description=EMPTY_BODY_DESCRIPTION,
    responses=LEGACY_RESPONSES,
)
@mapped(LEGACY_ERRORS)
def api_infer_coupled_structure(body: CoupledSystemBody):
    """Runs the class-axiom inference over a coupled system's connected instances (deriving existential and
    cardinality restrictions from the instance structure) and persists the result. Runs on the in-memory
    Owlready2 path."""
    with SEMANTIC_LOCK:
        reload_ontology_from_graphdb()
        infer_coupled_system_structure(body.coupled_system)
        save_onto()
    return ''


@get_route(
    '/get_instance_properties_recursively/',
    tags=['semantic'],
    operation_id='getInstancePropertiesRecursively',
    summary="Get an instance's properties as a nested structure",
    response_model=NestedProperties,
    response_description='Nested property structure.',
    responses=LEGACY_RESPONSES,
)
@mapped(LEGACY_ERRORS)
def api_get_instance_properties_recursively(
    instance: str = Query(description='Instance identifier.'),
    depth: int = Query(1, description='Recursion depth.'),
    recursive: bool = Query(False, description='Unlimited recursion when true.'),
):
    """Returns the instance's properties with linked instances expanded in place down to `depth` levels (or
    without limit when `recursive` is true). Property names lose the `has_` prefix; single-valued properties are
    returned as scalars, multi-valued ones as arrays. Runs on the in-memory Owlready2 path."""
    with SEMANTIC_LOCK:
        reload_ontology_from_graphdb()
        return get_instance_properties_recursively(instance, depth, recursive)


# --- files ---


@router.post(
    '/save_onto/',
    tags=['files'],
    operation_id='saveOnto',
    summary='Persist the in-memory ontology to GraphDB',
    status_code=201,
    response_model=EmptyBody,
    response_description=EMPTY_BODY_DESCRIPTION,
    responses=LEGACY_RESPONSES,
)
@mapped(LEGACY_ERRORS)
def api_save_onto():
    """Pushes the current in-memory Owlready2 model to the GraphDB named graph."""
    with SEMANTIC_LOCK:
        save_onto()
    return ''


def ontology_bytes():
    """Serialises the current ontology to disk and returns the bytes while the lock is still held."""
    save_locally()
    with open(get_onto_path(), 'rb') as ontology_file:
        return ontology_file.read()


@get_route(
    '/save_locally/',
    tags=['files'],
    operation_id='saveLocally',
    summary='Download the ontology as an OWL file (inline)',
    response_class=RdfXmlResponse,
    response_description='The ontology file.',
    responses=FILE_LEGACY_RESPONSES,
)
@mapped(LEGACY_ERRORS)
def api_save_locally():
    """Reloads the ontology from GraphDB, serialises it to RDF/XML and returns the file."""
    with SEMANTIC_LOCK:
        reload_ontology_from_graphdb()
        data = ontology_bytes()
    return RdfXmlResponse(content=data, headers={'Content-Disposition': 'inline; filename="onto.owl"'})


@get_route(
    '/download_owl/',
    tags=['files'],
    operation_id='downloadOwl',
    summary='Download the ontology as an OWL file (attachment)',
    response_class=RdfXmlResponse,
    response_description='The ontology file as an attachment.',
    responses=FILE_DOWNLOAD_RESPONSES,
)
@mapped(DOWNLOAD_ERRORS)
def api_download_owl():
    """Reloads the ontology from GraphDB, serialises it to RDF/XML and returns the file as a download attachment."""
    with SEMANTIC_LOCK:
        reload_ontology_from_graphdb()
        data = ontology_bytes()
    return RdfXmlResponse(content=data, headers={'Content-Disposition': 'attachment; filename="onto.owl"'})


# --- legacy reads ---


@get_route(
    '/get_class_hierarchy/',
    tags=['legacy'],
    operation_id='getClassHierarchy',
    summary='Map root classes to their subclasses',
    response_model=dict[str, list[str]],
    response_description='Root-class to subclasses mapping.',
    responses=LEGACY_RESPONSES,
)
@mapped(LEGACY_ERRORS)
def api_get_class_hierarchy():
    """Returns a mapping from each root class (no named parent) to the list of its direct subclasses. Superseded by
    `get_class_hierarchy_metadata` for the explorer UI."""
    return get_class_hierarchy()


@get_route(
    '/get_class_properties_recursively/',
    tags=['legacy'],
    operation_id='getClassPropertiesRecursively',
    summary="Get a class's restriction axioms as nested structures",
    response_model=list[ClassAxiom],
    response_description='List of class axioms.',
    responses=LEGACY_RESPONSES,
)
@mapped(LEGACY_ERRORS)
def api_get_class_properties_recursively(
    class_name: str = Query(alias='class', description='Class name.'),
    depth: int = Query(1, description='Recursion depth.'),
    recursive: bool = Query(False, description='Unlimited recursion when true.'),
):
    """Returns the class's restriction axioms (property, cardinality, target value) with class-valued targets
    expanded recursively down to `depth` levels (or without limit when `recursive` is true). Runs on the in-memory
    Owlready2 path."""
    with SEMANTIC_LOCK:
        reload_ontology_from_graphdb()
        return get_class_properties_recursively(class_name, depth, recursive)


@get_route(
    '/get_class_instances/',
    tags=['legacy'],
    operation_id='getClassInstances',
    summary='List instance identifiers of a class',
    response_model=list[str],
    response_description='Instance identifiers.',
    responses=LEGACY_RESPONSES,
)
@mapped(LEGACY_ERRORS)
def api_get_class_instances(class_name: str = Query(alias='class', description='Class name.')):
    """Returns the identifiers of all instances of the class (including subclass instances). Superseded by
    `get_class_instance_summaries` for the explorer UI."""
    return get_class_instances(class_name)


app.include_router(router)


if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=5000)
