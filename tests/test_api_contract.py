"""HTTP contract of the API layer, pinned route by route: the status code for
each failure class, the required-parameter messages, the empty-body creations,
and how query and body flags reach the core functions. Offline: every core
call is patched."""
import os
import sys
import unittest
from contextlib import ExitStack
from unittest.mock import patch

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from api import app, error_floor
from main import GraphDBError
from routers import ROUTERS

PREFIX = '/api/v1.0/'

# Module of each route, where its core calls are looked up and therefore patched.
MODULE_OF = {route.path: route.endpoint.__module__ for router in ROUTERS for route in router.routes}


class UnexpectedFailure(Exception):
    """A failure that is neither a GraphDB nor a validation error."""


# Failure-class -> status mappings the routes implement.
EXPLORER = {GraphDBError: 503, ValueError: 400, UnexpectedFailure: 500}
LEGACY = {GraphDBError: 400, ValueError: 400, UnexpectedFailure: 400}
DOWNLOAD = {GraphDBError: 500, ValueError: 500, UnexpectedFailure: 500}

# Owlready2 routes reload the ontology first and persist afterwards; both are
# patched out so the table only exercises the HTTP layer.
SEMANTIC_SIDE_EFFECTS = ('reload_ontology_from_graphdb', 'save_onto')

CLASS_METADATA = {'id': 'solver', 'label': 'solver', 'descriptions': [], 'superclasses': [], 'subclasses': [], 'restrictions': [], 'equivalent_classes': []}
INSTANCE_METADATA = {'id': 'i', 'label': 'i', 'types': [], 'properties': []}
DELETION_PREVIEW = {'instance': 'i', 'deleted': ['i'], 'kept': [], 'unlinked_from': []}

ROUTES = [
    # path, method, request, core function, core result, success status, success body, failure mapping
    ('get_class_hierarchy_metadata/', 'GET', {}, 'get_class_hierarchy_metadata', [{'class': 'c', 'parents': []}], 200, [{'class': 'c', 'parents': []}], EXPLORER),
    ('get_class_instance_summaries/', 'GET', {'query': {'class': 'solver'}}, 'get_class_instance_summaries', [], 200, [], EXPLORER),
    ('search/', 'GET', {'query': {'q': 'x'}}, 'search_entities', {'classes': [], 'instances': []}, 200, {'classes': [], 'instances': []}, EXPLORER),
    ('get_class_metadata/', 'GET', {'query': {'class': 'solver'}}, 'get_class_metadata', CLASS_METADATA, 200, CLASS_METADATA, EXPLORER),
    ('get_instance_property_metadata/', 'GET', {'query': {'instance': 'i'}}, 'get_instance_property_metadata', INSTANCE_METADATA, 200, INSTANCE_METADATA, EXPLORER),
    ('create_instance/', 'POST', {'json': {'property': 'p', 'parent': 'i', 'data': {}}}, 'create_instance_sparql', 'instance_new', 201, 'instance_new', EXPLORER),
    ('create_class_instance/', 'POST', {'json': {'class': 'solver', 'label': 'L'}}, 'create_class_instance_sparql', 'instance_new', 201, 'instance_new', EXPLORER),
    ('add_values/', 'POST', {'json': {'instance': 'i', 'data': {}}}, 'add_values_sparql', None, 201, '', EXPLORER),
    ('replace_values/', 'POST', {'json': {'instance': 'i', 'data': {}}}, 'replace_values_sparql', None, 201, '', EXPLORER),
    ('replace_properties/', 'POST', {'json': {'instance': 'i', 'data': {}}}, 'replace_properties_sparql', None, 201, '', EXPLORER),
    ('replace_value/', 'POST', {'json': {'instance': 'i', 'property': 'p', 'old_value': {'kind': 'literal', 'value': 1}, 'new_value': {'kind': 'literal', 'value': 2}}}, 'replace_value_sparql', None, 201, '', EXPLORER),
    ('delete_values/', 'POST', {'json': {'instance': 'i', 'properties': ['p']}}, 'delete_values_sparql', None, 201, '', EXPLORER),
    ('delete_value/', 'POST', {'json': {'instance': 'i', 'property': 'p', 'value': 1}}, 'delete_value_sparql', {'target': 't', 'deleted': [], 'kept': []}, 200, {'status': 'success', 'target': 't', 'deleted': [], 'kept': []}, EXPLORER),
    ('get_value_deletion_preview/', 'GET', {'query': {'instance': 'i', 'property': 'p', 'target': 't'}}, 'get_value_deletion_preview', {'target': 't', 'deleted': [], 'kept': []}, 200, {'target': 't', 'deleted': [], 'kept': []}, EXPLORER),
    ('delete_instance/', 'POST', {'json': {'instance': 'i'}}, 'delete_instance_sparql', {'instance': 'i', 'deleted': ['i'], 'kept': [], 'unlinked_from': []}, 200, {'status': 'success', 'instance': 'i', 'deleted': ['i'], 'kept': [], 'unlinked_from': []}, EXPLORER),
    ('get_instance_deletion_preview/', 'GET', {'query': {'instance': 'i'}}, 'get_instance_deletion_preview', DELETION_PREVIEW, 200, DELETION_PREVIEW, EXPLORER),
    ('import_coupled_kratos/', 'POST', {'json': {'data': {}, 'label': 'L'}}, 'import_coupled_kratos', 'instance_new', 201, 'instance_new', LEGACY),
    ('export_coupled_kratos/', 'POST', {'json': {'coupled_system': 'i'}}, 'export_coupled_kratos', {'problem_data': {}}, 201, {'problem_data': {}}, LEGACY),
    ('create_coupled/', 'POST', {'json': {'label': 'L'}}, 'create_coupled', 'instance_new', 201, 'instance_new', LEGACY),
    ('copy_instance/', 'POST', {'json': {'instance': 'i'}}, 'copy_instance', 'instance_new', 201, 'instance_new', LEGACY),
    ('copy_instance_recursively/', 'POST', {'json': {'instance': 'i'}}, 'copy_instance_recursively', 'instance_new', 201, 'instance_new', LEGACY),
    ('infer_coupled_structure/', 'POST', {'json': {'coupled_system': 'i'}}, 'infer_coupled_system_structure', None, 201, '', LEGACY),
    ('get_instance_properties_recursively/', 'GET', {'query': {'instance': 'i'}}, 'get_instance_properties_recursively', {'label': 'x'}, 200, {'label': 'x'}, LEGACY),
    ('get_class_properties_recursively/', 'GET', {'query': {'class': 'solver'}}, 'get_class_properties_recursively', [{'property': 'p', 'cardinality': None, 'value': 'c'}], 200, [{'property': 'p', 'cardinality': None, 'value': 'c'}], LEGACY),
    ('get_class_hierarchy/', 'GET', {}, 'get_class_hierarchy', {'solver': []}, 200, {'solver': []}, LEGACY),
    ('get_class_instances/', 'GET', {'query': {'class': 'solver'}}, 'get_class_instances', ['i'], 200, ['i'], LEGACY),
    ('save_onto/', 'POST', {}, 'save_onto', None, 201, '', LEGACY),
    ('save_locally/', 'GET', {}, 'save_locally', None, None, None, LEGACY),
    ('download_owl/', 'GET', {}, 'save_locally', None, None, None, DOWNLOAD),
]

# Required parameters: status 400 and an error naming every missing one.
MISSING = [
    ('create_class_instance/', 'POST', {'json': {}}, ['class', 'label']),
    ('replace_value/', 'POST', {'json': {}}, ['instance', 'property', 'old_value', 'new_value']),
    ('delete_value/', 'POST', {'json': {}}, ['instance', 'property', 'value']),
    ('delete_instance/', 'POST', {'json': {}}, ['instance']),
    ('delete_instance/', 'POST', {}, ['instance']),
    ('replace_value/', 'POST', {}, ['instance', 'property', 'old_value', 'new_value']),
    ('get_class_metadata/', 'GET', {}, ['class']),
    ('get_instance_property_metadata/', 'GET', {}, ['instance']),
    ('get_value_deletion_preview/', 'GET', {}, ['instance', 'property', 'target']),
    ('get_instance_deletion_preview/', 'GET', {}, ['instance']),
    ('search/', 'GET', {}, ['q']),
]

# Type-checked parameters: status 400 and an error naming the parameter.
ILL_TYPED = [
    ('delete_value/', 'POST', {'json': {'instance': 'i', 'property': 'p', 'value': 1, 'cascade': 'yes'}}, 'cascade'),
    ('delete_instance/', 'POST', {'json': {'instance': 'i', 'cascade': 'yes'}}, 'cascade'),
    ('get_instance_deletion_preview/', 'GET', {'query': {'instance': 'i', 'cascade': 'maybe'}}, 'cascade'),
    ('search/', 'GET', {'query': {'q': 'x', 'limit': 'abc'}}, 'limit'),
]


def core_patches(path, target, **outcome):
    """Patches the route's core call where its router binds it, and stubs reload/persist in main and in that module."""
    module = MODULE_OF[PREFIX + path]
    patches = [patch(f'{module}.{target}', **outcome)]
    for name in SEMANTIC_SIDE_EFFECTS:
        if name == target:
            continue
        patches.append(patch(f'main.{name}'))
        if hasattr(sys.modules[module], name):
            patches.append(patch(f'{module}.{name}'))
    return patches


def call(client, method, path, request):
    """Performs a request and returns (status, decoded JSON body or None)."""
    response = client.request(method, PREFIX + path, json=request.get('json'), params=request.get('query'))
    try:
        body = response.json()
    except ValueError:
        body = None
    return response.status_code, body


class TestRouteContract(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_success_status_and_body(self):
        for path, method, request, target, result, status, body, _ in ROUTES:
            if status is None:
                continue
            with self.subTest(path=path), ExitStack() as stack:
                for active in core_patches(path, target, return_value=result):
                    stack.enter_context(active)
                got_status, got_body = call(self.client, method, path, request)
                self.assertEqual(got_status, status)
                self.assertEqual(got_body, body)

    def test_failure_status_and_error_body(self):
        for path, method, request, target, _, _, _, mapping in ROUTES:
            for failure, status in mapping.items():
                with self.subTest(path=path, failure=failure.__name__), ExitStack() as stack:
                    for active in core_patches(path, target, side_effect=failure('boom')):
                        stack.enter_context(active)
                    got_status, got_body = call(self.client, method, path, request)
                    self.assertEqual(got_status, status)
                    self.assertEqual(got_body, {'error': 'boom'})

    def test_health_failure_bodies(self):
        for failure, status in ((GraphDBError, 503), (UnexpectedFailure, 500)):
            with self.subTest(failure=failure.__name__):
                with patch('routers.system.get_graphdb_health', side_effect=failure('down')):
                    got_status, got_body = call(self.client, 'GET', 'health/', {})
                self.assertEqual(got_status, status)
                self.assertEqual(got_body['status'], 'error')
                self.assertEqual(got_body['graphdb'], 'unavailable')
                self.assertEqual(got_body['error'], 'down')
                self.assertIn('repository', got_body)

    def test_missing_parameters_are_all_named(self):
        for path, method, request, names in MISSING:
            with self.subTest(path=path):
                got_status, got_body = call(self.client, method, path, request)
                self.assertEqual(got_status, 400)
                for name in names:
                    self.assertIn(name, got_body['error'])

    def test_ill_typed_parameters(self):
        for path, method, request, parameter in ILL_TYPED:
            with self.subTest(path=path):
                got_status, got_body = call(self.client, method, path, request)
                self.assertEqual(got_status, 400)
                self.assertIn(parameter, got_body['error'])

    def test_cascade_defaults_to_true_and_false_is_forwarded(self):
        with patch('routers.mutations.delete_instance_sparql', return_value={'instance': 'i', 'deleted': [], 'kept': [], 'unlinked_from': []}) as core:
            call(self.client, 'POST', 'delete_instance/', {'json': {'instance': 'i'}})
            core.assert_called_with('i', cascade=True)
            call(self.client, 'POST', 'delete_instance/', {'json': {'instance': 'i', 'cascade': False}})
            core.assert_called_with('i', cascade=False)
        with patch('routers.explorer.get_instance_deletion_preview', return_value={}) as core:
            call(self.client, 'GET', 'get_instance_deletion_preview/', {'query': {'instance': 'i', 'cascade': 'false'}})
            core.assert_called_with('i', cascade=False)

    def test_depth_and_recursive_query_flags_are_forwarded(self):
        with patch('routers.semantic.reload_ontology_from_graphdb'), \
                patch('routers.semantic.get_instance_properties_recursively', return_value={}) as core:
            call(self.client, 'GET', 'get_instance_properties_recursively/', {'query': {'instance': 'i'}})
            core.assert_called_with('i', 1, False)
            call(self.client, 'GET', 'get_instance_properties_recursively/', {'query': {'instance': 'i', 'depth': '2', 'recursive': 'True'}})
            core.assert_called_with('i', 2, True)
        with patch('routers.legacy.reload_ontology_from_graphdb'), \
                patch('routers.legacy.get_class_properties_recursively', return_value={}) as core:
            call(self.client, 'GET', 'get_class_properties_recursively/', {'query': {'class': 'c', 'depth': '3', 'recursive': 'True'}})
            core.assert_called_with('c', 3, True)

    def test_copy_body_flags_are_forwarded(self):
        with patch('routers.semantic.reload_ontology_from_graphdb'), patch('routers.semantic.save_onto'), \
                patch('routers.semantic.copy_instance_recursively', return_value='instance_new') as core:
            call(self.client, 'POST', 'copy_instance_recursively/', {'json': {'instance': 'i', 'parent': 'p', 'data': {'a': 1}, 'depth': 2, 'recursive': 'True'}})
            core.assert_called_with('i', 'p', {'a': 1}, 2, True)
            call(self.client, 'POST', 'copy_instance_recursively/', {'json': {'instance': 'i'}})
            core.assert_called_with('i', None, None, 1, False)
            # The Python client package sends a null depth for an unlimited copy.
            call(self.client, 'POST', 'copy_instance_recursively/', {'json': {'instance': 'i', 'depth': None, 'recursive': True}})
            core.assert_called_with('i', None, None, None, True)

    def test_search_defaults(self):
        with patch('routers.explorer.search_entities', return_value={'classes': [], 'instances': []}) as core:
            call(self.client, 'GET', 'search/', {'query': {'q': 'wing'}})
            args = core.call_args[0]
            self.assertEqual(args[:2], ('wing', 'all'))
            self.assertIsInstance(args[2], int)
            call(self.client, 'GET', 'search/', {'query': {'q': 'wing', 'type': 'class', 'limit': '5'}})
            core.assert_called_with('wing', 'class', 5)

    def test_head_and_malformed_json(self):
        with patch('routers.system.get_graphdb_health', return_value={'status': 'ok'}):
            self.assertEqual(self.client.head(PREFIX + 'health/').status_code, 200)
        malformed = self.client.post(PREFIX + 'delete_instance/', content=b'{bad', headers={'Content-Type': 'application/json'})
        self.assertEqual(malformed.status_code, 400)
        self.assertTrue(malformed.json()['error'].startswith('request: '))

    def test_union_errors_name_the_field_once(self):
        got_status, got_body = call(self.client, 'POST', 'delete_value/', {'json': {'instance': 'i', 'property': 'p', 'value': {'value': 1}}})
        self.assertEqual(got_status, 400)
        self.assertTrue(got_body['error'].startswith('value: '), got_body)
        self.assertNotIn('union', got_body['error'])
        self.assertNotIn(';', got_body['error'])

    def test_core_result_outside_the_contract_is_reported_without_internals(self):
        with patch('routers.explorer.get_value_deletion_preview', return_value={'target': 't', 'deleted': [], 'kept': [], 'surprise': 1}):
            got_status, got_body = call(self.client, 'GET', 'get_value_deletion_preview/', {'query': {'instance': 'i', 'property': 'p', 'target': 't'}})
        self.assertEqual(got_status, 500)
        self.assertTrue(got_body['error'].startswith('Response does not match the API contract'), got_body)
        self.assertNotIn('/home', got_body['error'])

    def test_typed_value_targets_reach_the_core_as_dicts(self):
        with patch('routers.mutations.replace_value_sparql') as core:
            call(self.client, 'POST', 'replace_value/', {'json': {
                'instance': 'i', 'property': 'p',
                'old_value': {'kind': 'literal', 'value': 'a', 'datatype': 'http://www.w3.org/2001/XMLSchema#string'},
                'new_value': {'kind': 'object', 'id': 'instance_2'},
            }})
            core.assert_called_with('i', 'p', {'kind': 'literal', 'value': 'a', 'datatype': 'http://www.w3.org/2001/XMLSchema#string'}, {'kind': 'object', 'id': 'instance_2'})
        with patch('routers.mutations.delete_value_sparql', return_value={'target': None, 'deleted': [], 'kept': []}) as core:
            call(self.client, 'POST', 'delete_value/', {'json': {'instance': 'i', 'property': 'p', 'value': 'plain'}})
            core.assert_called_with('i', 'p', 'plain', cascade=True)

    def test_spec_route_and_unknown_route(self):
        response = self.client.get(PREFIX + 'openapi.yaml')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.text.startswith('openapi:'))
        unknown = self.client.get(PREFIX + 'no_such_route/')
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(unknown.json(), {'error': 'Not Found'})
        self.assertEqual(self.client.get('/').status_code, 404)

    def test_every_route_has_a_contract_row(self):
        """A route added without a row here is neither status- nor message-checked."""
        listed = {PREFIX + path for path, *_ in ROUTES} | {PREFIX + 'health/', PREFIX + 'openapi.yaml'}
        self.assertEqual(set(MODULE_OF), listed)

    def test_direct_sparql_routers_bind_no_owlready_side_effects(self):
        """A route with the explorer failure mapping runs on direct SPARQL: its module never reloads or persists the Owlready2 world."""
        direct = {MODULE_OF[PREFIX + path] for path, *_, mapping in ROUTES if mapping is EXPLORER}
        for module in sorted(direct):
            self.assertFalse(set(SEMANTIC_SIDE_EFFECTS) & vars(sys.modules[module]).keys(), module)

    def test_unmapped_failure_answers_in_the_error_shape(self):
        """The floor turns an escaped failure into the JSON error body, with CORS headers."""
        probe = FastAPI()
        probe.middleware('http')(error_floor)
        probe.add_middleware(CORSMiddleware, allow_origins=['http://localhost:3000'])
        probe.add_api_route('/boom', lambda: 1 / 0)
        response = TestClient(probe, raise_server_exceptions=False).get('/boom', headers={'Origin': 'http://localhost:3000'})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {'error': 'division by zero'})
        self.assertEqual(response.headers.get('access-control-allow-origin'), 'http://localhost:3000')

    def test_slashless_path_redirects_to_the_route(self):
        """The Python client package posts without trailing slashes and relies on the redirect."""
        response = self.client.post(PREFIX + 'add_values', json={'instance': 'i', 'data': {}}, follow_redirects=False)
        self.assertIn(response.status_code, (307, 308))
        self.assertTrue(response.headers['location'].endswith(PREFIX + 'add_values/'))
        with patch('routers.mutations.add_values_sparql'):
            followed = self.client.post(PREFIX + 'add_values', json={'instance': 'i', 'data': {}})
        self.assertEqual(followed.status_code, 201)

    def test_semantic_routes_run_one_at_a_time(self):
        """Two overlapping Owlready2 requests never interleave their reload/persist window."""
        import threading
        import time
        inside = []
        overlaps = []

        def slow_export(name):
            inside.append(name)
            if len(inside) > 1:
                overlaps.append(name)
            time.sleep(0.02)
            inside.remove(name)
            return {}

        with patch('routers.semantic.reload_ontology_from_graphdb'), patch('routers.semantic.export_coupled_kratos', side_effect=slow_export):
            threads = [threading.Thread(target=call, args=(self.client, 'POST', 'export_coupled_kratos/', {'json': {'coupled_system': f'i{n}'}})) for n in range(3)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual(overlaps, [])


if __name__ == '__main__':
    unittest.main()
