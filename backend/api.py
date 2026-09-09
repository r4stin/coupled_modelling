"""HTTP layer of the knowledge base: the FastAPI application, assembled from one
router per tag (routers/) over the framework-agnostic core in main.py. The
OpenAPI document is generated from the routes and served as YAML at
/api/v1.0/openapi.yaml. The web explorer lives in the separate
coupled-modelling-frontend repository."""
import os
import re
import traceback

import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from routers import ROUTERS
from routing import API_PREFIX, error_response

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


for included in ROUTERS:
    app.include_router(included)
# No module-level router survives the loop: the routes live in routers/.
del included


if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=5000)
