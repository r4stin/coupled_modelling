"""Request bodies and response shapes of the API; the OpenAPI document is generated from them.
Responses are typed as dicts: optional keys stay absent when the core omits them, and an undeclared
key is a contract violation (the response fails validation instead of being silently dropped)."""
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StrictBool
from pydantic.json_schema import SkipJsonSchema
from typing_extensions import NotRequired, TypeAliasType, TypedDict

ScalarValue = TypeAliasType('ScalarValue', Annotated[Union[str, int, float, bool], Field(description='A literal value (string, number or boolean).')])

InstanceId = TypeAliasType(
    'InstanceId',
    Annotated[
        str,
        Field(
            description='Local identifier of an instance (UUID-based for instances created through the API).',
            examples=['instance_550e8400-e29b-41d4-a716-446655440000'],
        ),
    ],
)

PropertyDataMap = TypeAliasType(
    'PropertyDataMap',
    Annotated[
        dict[str, Union[ScalarValue, list[ScalarValue]]],
        Field(
            description=(
                'Property-name to value(s) mapping. Keys are property names without the `has_` prefix '
                '(plus `label` for `rdfs:label`). Values are scalars or arrays of scalars. Whether plain '
                'strings on object properties are label-resolved to object references is documented per '
                'endpoint; the replace endpoints accept only non-string literals (numbers, booleans), '
                '`label` strings, and explicit `instance*` references.'
            ),
            examples=[{'echo_level': 1, 'print_colors': False}],
        ),
    ],
)

KratosParameters = TypeAliasType(
    'KratosParameters',
    Annotated[dict[str, Any], Field(description='Kratos CoSimulation parameters JSON (nested solver, coupling and data-transfer configuration).')],
)

NestedProperties = TypeAliasType(
    'NestedProperties',
    Annotated[
        dict[str, Any],
        Field(
            description=(
                'Recursive property structure: keys are property names (without the `has_` prefix), values are '
                "scalars, arrays, or one-key objects mapping a linked instance's identifier to its own nested properties."
            ),
            examples=[{'label': 'FSI Mok benchmark', 'problem_data': {'problem_data_1': {'parallel_type': 'OpenMP', 'echo_level': 1}}}],
        ),
    ],
)

EMPTY_BODY_DESCRIPTION = 'The operation succeeded. The body is an empty JSON string.'
EmptyBody = TypeAliasType('EmptyBody', Annotated[Literal[''], Field(description=EMPTY_BODY_DESCRIPTION)])


class Error(BaseModel):
    error: str = Field(description='Human-readable error message.')


# --- value targets (shared by requests and responses) ---


class ObjectValueTarget(BaseModel):
    """Targets an object-property triple pointing at the referenced instance."""

    kind: Literal['object']
    id: str = Field(description='Identifier of the linked instance the triple points at.')


class LiteralValueTarget(BaseModel):
    """Targets a literal triple; the datatype and language tag drive term serialization."""

    kind: Literal['literal']
    value: ScalarValue
    datatype: str | SkipJsonSchema[None] = Field(
        default=None,
        description='XSD datatype IRI of the literal (defaults to plain string serialization).',
        examples=['http://www.w3.org/2001/XMLSchema#integer'],
    )
    language: str | SkipJsonSchema[None] = Field(
        default=None, description='Language tag of the literal, required to match language-tagged triples ("value"@de).', examples=['de']
    )


ValueTarget = Annotated[Union[ObjectValueTarget, LiteralValueTarget], Field(discriminator='kind')]


def target_payload(value):
    """The dict form the core functions expect for a typed value target; scalars pass through."""
    return value.model_dump(exclude_unset=True) if isinstance(value, BaseModel) else value


# --- request bodies ---


class InstanceDataBody(BaseModel):
    instance: str = Field(description='Instance identifier.')
    data: PropertyDataMap


class CoupledSystemBody(BaseModel):
    coupled_system: str = Field(description='Identifier of the coupled-system instance.')


class CreateInstanceBody(BaseModel):
    property: str = Field(description='Class name of the new instance (also selects the `has_*` linking property).', examples=['solvers'])
    parent: str = Field(description='Identifier of the existing parent instance.')
    data: PropertyDataMap | SkipJsonSchema[None] = None


class CreateClassInstanceBody(BaseModel):
    class_name: str = Field(alias='class', description='Class to instantiate.', examples=['solvers'])
    label: str = Field(description='Human-readable label stored as `rdfs:label`.', examples=['Airfoil fluid solver'])


class ReplaceValueBody(BaseModel):
    instance: str = Field(description='Instance identifier.')
    property: str = Field(description='Property name (without the `has_` prefix).')
    old_value: ValueTarget = Field(description='The currently stored value to replace.')
    new_value: ValueTarget = Field(description='The replacement value.')


class DeleteValueBody(BaseModel):
    instance: str = Field(description='Instance identifier.')
    property: str = Field(description='Property name (without the `has_` prefix).', examples=['parallel_type'])
    value: Union[ValueTarget, ScalarValue] = Field(
        description='The value to delete. The typed forms delete the exact triple (correct datatype serialization); a bare scalar is matched by serialization guess.'
    )
    cascade: StrictBool = Field(default=True, description="Also delete the unlinked instance's owned subtree when nothing else reaches it.")


class DeleteValuesBody(BaseModel):
    instance: str = Field(description='Instance identifier.')
    properties: list[str] = Field(description='Property names whose values are removed (without the `has_` prefix).', examples=[['echo_level', 'parallel_type']])


class DeleteInstanceBody(BaseModel):
    instance: str = Field(description='Identifier of the instance to delete.')
    cascade: StrictBool = Field(default=True, description="Also delete the instance's owned subtree.")


class ImportKratosBody(BaseModel):
    data: KratosParameters
    label: str = Field(description='Label for the imported coupled system.', examples=['FSI Mok benchmark'])


class CreateCoupledBody(BaseModel):
    label: str = Field(description='Label for the new coupled system.')


class CopyInstanceBody(BaseModel):
    instance: str = Field(description='Identifier of the instance to copy.')
    parent: str | SkipJsonSchema[None] = Field(default=None, description='Optional parent instance to attach the copy to.')
    data: PropertyDataMap | SkipJsonSchema[None] = None


class CopyInstanceRecursivelyBody(CopyInstanceBody):
    depth: int | None = Field(default=1, description='Recursion depth (levels of linked instances to copy); null for no limit.')
    recursive: bool = Field(default=False, description='Unlimited recursion when true.')


# --- responses ---

# A core result with a key the contract does not declare must fail loudly, not vanish.
CONTRACT = ConfigDict(extra='forbid')


class HealthOk(TypedDict):
    __pydantic_config__ = CONTRACT
    status: Literal['ok']
    graphdb: Literal['connected']
    repository: Annotated[str, Field(description='Name of the configured GraphDB repository.', examples=['coupled_modelling'])]


class HealthError(TypedDict):
    __pydantic_config__ = CONTRACT
    status: Literal['error']
    graphdb: Literal['unavailable']
    repository: Annotated[str, Field(description='Name of the configured GraphDB repository.')]
    error: Annotated[str, Field(description='Underlying connection error message.')]


class DeletionSets(TypedDict):
    """What a deletion removes and what it leaves in place."""
    __pydantic_config__ = CONTRACT

    deleted: Annotated[
        list[str], Field(description='Identifiers the deletion removes, the root of the collected subtree first; empty when nothing is collected.')
    ]
    kept: Annotated[
        list[str],
        Field(
            description=(
                'Reachable instances kept because they are still reachable from outside the collected subtree '
                '(an instance linked from elsewhere, or a coupled system, plus everything below it).'
            )
        ),
    ]


class DeletionPreview(DeletionSets):
    __pydantic_config__ = CONTRACT
    instance: Annotated[str, Field(description='Identifier of the instance the deletion applies to.')]
    unlinked_from: Annotated[list[str], Field(description='Surviving instances whose link to the deleted instance is removed.')]


class UnlinkResult(DeletionSets):
    __pydantic_config__ = CONTRACT
    target: Annotated[
        str | None,
        Field(
            description=(
                'The unlinked instance, or null when the value was a literal. It appears in `deleted` when collected, '
                'in `kept` when it survives (still linked from elsewhere, a coupled system, the link holder itself, '
                '`cascade` off, or the link was not stored), and in neither when it is not an individual (a dangling '
                'reference or a class). The instance holding the link is never collected; it is listed in `kept` when '
                'the target is collected and a link below the target leads back to it.'
            )
        ),
    ]


class InstanceDeletionResult(DeletionPreview):
    __pydantic_config__ = CONTRACT
    status: Literal['success']


class ValueDeletionResult(UnlinkResult):
    __pydantic_config__ = CONTRACT
    status: Literal['success']


ClassHierarchyEntry = TypedDict(
    'ClassHierarchyEntry',
    {
        'class': Annotated[str, Field(description='Local class name.', examples=['convergence_accelerators'])],
        'parents': Annotated[list[str], Field(description='Direct named superclasses (empty for root classes).')],
    },
)
ClassHierarchyEntry.__pydantic_config__ = CONTRACT


class PreviewItem(TypedDict):
    __pydantic_config__ = CONTRACT
    property: Annotated[str, Field(description='Property name.')]
    value: ScalarValue
    kind: Annotated[Literal['literal', 'object'], Field(description='Whether the value is a typed literal or the resolved label of a linked instance.')]


class InstanceSummary(TypedDict):
    __pydantic_config__ = CONTRACT
    id: Annotated[str, Field(description='Local instance identifier.')]
    label: Annotated[str, Field(description='Preferred label (English first), falling back to the identifier.')]
    types: Annotated[list[str], Field(description='Direct class names of the instance.')]
    property_preview: Annotated[list[PreviewItem], Field(description='Up to three property values for compact display (literals first).')]
    preview_truncated: Annotated[bool, Field(description='True when the instance has more values than shown in the preview.')]


class SearchClassResult(TypedDict):
    __pydantic_config__ = CONTRACT
    id: Annotated[str, Field(description='Local class name.')]


class SearchResults(TypedDict):
    __pydantic_config__ = CONTRACT
    classes: Annotated[list[SearchClassResult], Field(description='Matching classes (empty when `type=instance`).')]
    instances: Annotated[list[InstanceSummary], Field(description='Matching instances (empty when `type=class`).')]


class NamedReference(TypedDict):
    __pydantic_config__ = CONTRACT
    id: Annotated[str, Field(description='Local name of the referenced entity.')]
    label: Annotated[str, Field(description='Preferred label, falling back to the local name.')]


class ObjectPropertyValue(InstanceSummary):
    """A linked instance: the summary shape plus the value kind."""

    __pydantic_config__ = CONTRACT
    kind: Literal['object']


class LiteralPropertyValue(TypedDict):
    __pydantic_config__ = CONTRACT
    kind: Literal['literal']
    value: ScalarValue
    datatype: Annotated[str, Field(description='XSD datatype IRI of the literal.', examples=['http://www.w3.org/2001/XMLSchema#integer'])]
    language: NotRequired[Annotated[str, Field(description='Language tag, when present on the literal.')]]


PropertyValue = Annotated[Union[ObjectPropertyValue, LiteralPropertyValue], Field(discriminator='kind')]


class InstancePropertyGroup(TypedDict):
    __pydantic_config__ = CONTRACT
    property: Annotated[str, Field(description='Property name without the `has_` prefix.')]
    values: list[PropertyValue]


class InstanceMetadata(TypedDict):
    __pydantic_config__ = CONTRACT
    id: Annotated[str, Field(description='Local instance identifier.')]
    label: Annotated[str, Field(description='Preferred label, falling back to the identifier.')]
    types: Annotated[list[str], Field(description='Project-local class names of the instance.')]
    properties: Annotated[list[InstancePropertyGroup], Field(description='Direct properties, sorted by property name.')]


class RestrictionTarget(TypedDict):
    __pydantic_config__ = CONTRACT
    id: Annotated[str, Field(description='Local name of the target class, or the raw value for literal targets.')]
    label: Annotated[str, Field(description='Display label ("A & B" for intersections, "Anonymous Class (id)" for unresolved blank nodes).')]
    value: NotRequired[ScalarValue]
    datatype: NotRequired[Annotated[str, Field(description='XSD datatype IRI (literal targets only).')]]
    language: NotRequired[Annotated[str, Field(description='Language tag (literal targets only).')]]
    members: NotRequired[Annotated[list[NamedReference], Field(description='Named member classes (intersection targets only).')]]


RestrictionKind = Literal[
    'some_values_from',
    'all_values_from',
    'has_value',
    'cardinality',
    'min_cardinality',
    'max_cardinality',
    'qualified_cardinality',
    'min_qualified_cardinality',
    'max_qualified_cardinality',
]


class Restriction(TypedDict):
    __pydantic_config__ = CONTRACT
    property: NamedReference
    kind: Annotated[RestrictionKind, Field(description='Type of OWL restriction.')]
    cardinality: NotRequired[Annotated[Union[int, str], Field(description='Cardinality bound (cardinality restrictions only).')]]
    target_kind: NotRequired[Annotated[Literal['class', 'literal', 'bnode', 'intersection', 'data_range'], Field(description='Nature of the restriction target.')]]
    target: NotRequired[RestrictionTarget]


class ClassMetadata(TypedDict):
    __pydantic_config__ = CONTRACT
    id: Annotated[str, Field(description='Local class name.')]
    label: Annotated[str, Field(description='Class label (currently identical to the local name).')]
    descriptions: Annotated[list[str], Field(description='`rdfs:comment` and `skos:definition` annotations.')]
    superclasses: list[NamedReference]
    subclasses: list[NamedReference]
    restrictions: Annotated[list[Restriction], Field(description='Asserted OWL restriction axioms, sorted by property label.')]
    equivalent_classes: list[NamedReference]


class ClassAxiom(TypedDict):
    __pydantic_config__ = CONTRACT
    property: Annotated[str, Field(description='Restricted property name.')]
    cardinality: Annotated[int | None, Field(description='Cardinality bound, when the axiom is a cardinality restriction.')]
    value: Annotated[
        Union[str, list[Union[str, dict[str, Any]]]],
        Field(
            description=(
                'Target class name, the member class names of an intersection target, or one-key objects mapping '
                'a member class to its own axioms when expanded recursively.'
            )
        ),
    ]
