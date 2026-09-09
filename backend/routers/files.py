"""Ontology file downloads and persistence."""
from fastapi import APIRouter

from main import get_onto_path, reload_ontology_from_graphdb, save_locally, save_onto
from routing import (
    API_PREFIX,
    DOWNLOAD_ERRORS,
    FILE_DOWNLOAD_RESPONSES,
    FILE_LEGACY_RESPONSES,
    LEGACY_ERRORS,
    LEGACY_RESPONSES,
    SEMANTIC_LOCK,
    RdfXmlResponse,
    get_route,
    mapped,
)
from schemas import EMPTY_BODY_DESCRIPTION, EmptyBody

router = APIRouter(prefix=API_PREFIX, tags=['files'])


@router.post(
    '/save_onto/',
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
    router,
    '/save_locally/',
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
    router,
    '/download_owl/',
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
