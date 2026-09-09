"""Health and connection status, and the served contract."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from main import REPOSITORY, GraphDBError, get_graphdb_health
from routing import API_PREFIX, GRAPHDB_UNAVAILABLE, YamlResponse, get_route, openapi_yaml
from schemas import HealthError, HealthOk

router = APIRouter(prefix=API_PREFIX, tags=['system'])


def health_error(status, exc):
    return JSONResponse(
        status_code=status,
        content={'status': 'error', 'graphdb': 'unavailable', 'repository': REPOSITORY, 'error': str(exc)},
    )


@get_route(
    router,
    '/openapi.yaml',
    operation_id='getOpenApiSpec',
    summary='Download this OpenAPI specification',
    response_class=YamlResponse,
    response_description='The OpenAPI 3.1 specification in YAML.',
)
def api_openapi_spec(request: Request):
    """Serves the OpenAPI document generated from the running backend, so clients and tooling can generate typed bindings without a copy of the repository."""
    return YamlResponse(openapi_yaml(request.app))


@get_route(
    router,
    '/health/',
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
