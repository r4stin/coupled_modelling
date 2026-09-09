"""Stateless create/update/delete operations executed as direct SPARQL updates."""
from fastapi import APIRouter

from main import (
    add_values_sparql,
    create_class_instance_sparql,
    create_instance_sparql,
    delete_instance_sparql,
    delete_value_sparql,
    delete_values_sparql,
    replace_properties_sparql,
    replace_value_sparql,
    replace_values_sparql,
)
from routing import API_PREFIX, EXPLORER_ERRORS, EXPLORER_RESPONSES, mapped
from schemas import (
    EMPTY_BODY_DESCRIPTION,
    CreateClassInstanceBody,
    CreateInstanceBody,
    DeleteInstanceBody,
    DeleteValueBody,
    DeleteValuesBody,
    EmptyBody,
    InstanceDataBody,
    InstanceDeletionResult,
    InstanceId,
    ReplaceValueBody,
    ValueDeletionResult,
    target_payload,
)

router = APIRouter(prefix=API_PREFIX, tags=['mutations'])


@router.post(
    '/create_instance/',
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
