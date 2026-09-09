"""Owlready2 in-memory workflows (Kratos import/export, copying, inference)."""
import traceback

from fastapi import APIRouter, Query

from main import (
    copy_instance,
    copy_instance_recursively,
    create_coupled,
    export_coupled_kratos,
    get_instance_properties_recursively,
    import_coupled_kratos,
    infer_coupled_system_structure,
    reload_ontology_from_graphdb,
    save_onto,
)
from routing import API_PREFIX, LEGACY_ERRORS, LEGACY_RESPONSES, SEMANTIC_LOCK, get_route, mapped
from schemas import (
    EMPTY_BODY_DESCRIPTION,
    CopyInstanceBody,
    CopyInstanceRecursivelyBody,
    CoupledSystemBody,
    CreateCoupledBody,
    EmptyBody,
    ImportKratosBody,
    InstanceId,
    KratosParameters,
    NestedProperties,
)

router = APIRouter(prefix=API_PREFIX, tags=['semantic'])


@router.post(
    '/import_coupled_kratos/',
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
    router,
    '/get_instance_properties_recursively/',
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
