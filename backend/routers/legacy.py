"""Early read endpoints kept for compatibility; the explorer endpoints supersede them."""
from fastapi import APIRouter, Query

from main import get_class_hierarchy, get_class_instances, get_class_properties_recursively, reload_ontology_from_graphdb
from routing import API_PREFIX, LEGACY_ERRORS, LEGACY_RESPONSES, SEMANTIC_LOCK, get_route, mapped
from schemas import ClassAxiom

router = APIRouter(prefix=API_PREFIX, tags=['legacy'])


@get_route(
    router,
    '/get_class_hierarchy/',
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
    router,
    '/get_class_properties_recursively/',
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
    router,
    '/get_class_instances/',
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
