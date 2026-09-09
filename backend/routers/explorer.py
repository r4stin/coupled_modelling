"""Read-only metadata endpoints backing the web explorer (direct SPARQL)."""
from typing import Literal

from fastapi import APIRouter, Query
from pydantic.json_schema import SkipJsonSchema

from main import (
    SEARCH_RESULT_LIMIT,
    SEARCH_RESULT_LIMIT_MAX,
    get_class_hierarchy_metadata,
    get_class_instance_summaries,
    get_class_metadata,
    get_instance_deletion_preview,
    get_instance_property_metadata,
    get_value_deletion_preview,
    search_entities,
)
from routing import API_PREFIX, EXPLORER_ERRORS, EXPLORER_RESPONSES, get_route, mapped
from schemas import (
    ClassHierarchyEntry,
    ClassMetadata,
    DeletionPreview,
    Error,
    InstanceMetadata,
    InstanceSummary,
    SearchResults,
    UnlinkResult,
)

router = APIRouter(prefix=API_PREFIX, tags=['explorer'])


@get_route(
    router,
    '/get_class_hierarchy_metadata/',
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
    router,
    '/search/',
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
    router,
    '/get_class_instance_summaries/',
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
    router,
    '/get_class_metadata/',
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
    router,
    '/get_instance_property_metadata/',
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
    router,
    '/get_value_deletion_preview/',
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
    router,
    '/get_instance_deletion_preview/',
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
