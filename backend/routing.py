"""Route-declaration helpers shared by the routers in routers/: the API prefix,
the error shape, the failure-class mappings and the documented error responses,
the GET+HEAD registration, the non-JSON response classes, the one-at-a-time lock
of the Owlready2 routes and the YAML rendering of the contract."""
import functools
import threading
import traceback

import yaml
from fastapi.responses import JSONResponse, Response

from main import GraphDBError
from schemas import Error

API_PREFIX = '/api/v1.0'


def error_response(status, message):
    return JSONResponse(status_code=status, content={'error': message})


def get_route(router, path, **kwargs):
    """GET route that also answers HEAD (undocumented), as the previous framework did."""
    def decorate(endpoint):
        router.add_api_route(path, endpoint, methods=['GET'], **kwargs)
        router.add_api_route(path, endpoint, methods=['HEAD'], include_in_schema=False)
        return endpoint
    return decorate


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


def openapi_yaml(app):
    """The given app's contract as YAML, rendered once per process (the served file and the committed file share it)."""
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


def json_error(response):
    """An error response documented as JSON on a route whose success body is not JSON."""
    return {'description': response['description'], 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/Error'}}}}


FILE_LEGACY_RESPONSES = {400: json_error(BAD_REQUEST)}
FILE_DOWNLOAD_RESPONSES = {500: json_error(UNEXPECTED_ERROR)}
