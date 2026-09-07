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

from api import app, error_floor, router
from main import GraphDBError

PREFIX = '/api/v1.0/'


class UnexpectedFailure(Exception):
    """A failure that is neither a GraphDB nor a validation error."""


# Failure-class -> status mappings the routes implement.
EXPLORER = {GraphDBError: 503, ValueError: 400, UnexpectedFailure: 500}
LEGACY = {GraphDBError: 400, ValueError: 400, UnexpectedFailure: 400}
DOWNLOAD = {GraphDBError: 500, ValueError: 500, UnexpectedFailure: 500}

# Owlready2 routes reload the ontology first and persist afterwards; both are
# patched out so the table only exercises the HTTP layer.
SEMANTIC_SIDE_EFFECTS = ('reload_ontology_from_graphdb', 'save_onto')

ROUTES = [
    # path, method, request, core function, core result, success status, success body, failure mapping
    ('get_class_hierarchy_metadata/', 'GET', {}, 'get_class_hierarchy_metadata', [{'id': 'c'}], 200, [{'id': 'c'}], EXPLORER),
    ('get_class_instance_summaries/', 'GET', {'query': {'class': 'solver'}}, 'get_class_instance_summaries', [], 200, [], EXPLORER),
    ('search/', 'GET', {'query': {'q': 'x'}}, 'search_entities', {'classes': [], 'instances': []}, 200, {'classes': [], 'instances': []}, EXPLORER),
    ('get_class_metadata/', 'GET', {'query': {'class': 'solver'}}, 'get_class_metadata', {'id': 'solver'}, 200, {'id': 'solver'}, EXPLORER),
    ('get_instance_property_metadata/', 'GET', {'query': {'instance': 'i'}}, 'get_instance_property_metadata', {'id': 'i'}, 200, {'id': 'i'}, EXPLORER),
    ('create_instance/', 'POST', {'json': {'property': 'p', 'parent': 'i', 'data': {}}}, 'create_instance_sparql', 'instance_new', 201, 'instance_new', EXPLORER),
    ('create_class_instance/', 'POST', {'json': {'class': 'solver', 'label': 'L'}}, 'create_class_instance_sparql', 'instance_new', 201, 'instance_new', EXPLORER),
    ('add_values/', 'POST', {'json': {'instance': 'i', 'data': {}}}, 'add_values_sparql', None, 201, '', EXPLORER),
    ('replace_values/', 'POST', {'json': {'instance': 'i', 'data': {}}}, 'replace_values_sparql', None, 201, '', EXPLORER),
    ('replace_properties/', 'POST', {'json': {'instance': 'i', 'data': {}}}, 'replace_properties_sparql', None, 201, '', EXPLORER),
    ('replace_value/', 'POST', {'json': {'instance': 'i', 'property': 'p', 'old_value': 1, 'new_value': 2}}, 'replace_value_sparql', None, 201, '', EXPLORER),
    ('delete_values/', 'POST', {'json': {'instance': 'i', 'properties': ['p']}}, 'delete_values_sparql', None, 201, '', EXPLORER),
    ('delete_value/', 'POST', {'json': {'instance': 'i', 'property': 'p', 'value': 1}}, 'delete_value_sparql', {'target': 't', 'deleted': [], 'kept': []}, 200, {'status': 'success', 'target': 't', 'deleted': [], 'kept': []}, EXPLORER),
    ('get_value_deletion_preview/', 'GET', {'query': {'instance': 'i', 'property': 'p', 'target': 't'}}, 'get_value_deletion_preview', {'target': 't'}, 200, {'target': 't'}, EXPLORER),
    ('delete_instance/', 'POST', {'json': {'instance': 'i'}}, 'delete_instance_sparql', {'instance': 'i', 'deleted': ['i'], 'kept': [], 'unlinked_from': []}, 200, {'status': 'success', 'instance': 'i', 'deleted': ['i'], 'kept': [], 'unlinked_from': []}, EXPLORER),
    ('get_instance_deletion_preview/', 'GET', {'query': {'instance': 'i'}}, 'get_instance_deletion_preview', {'instance': 'i'}, 200, {'instance': 'i'}, EXPLORER),
    ('import_coupled_kratos/', 'POST', {'json': {'data': {}, 'label': 'L'}}, 'import_coupled_kratos', 'instance_new', 201, 'instance_new', LEGACY),
    ('export_coupled_kratos/', 'POST', {'json': {'coupled_system': 'i'}}, 'export_coupled_kratos', {'problem_data': {}}, 201, {'problem_data': {}}, LEGACY),
    ('create_coupled/', 'POST', {'json': {'label': 'L'}}, 'create_coupled', 'instance_new', 201, 'instance_new', LEGACY),
    ('copy_instance/', 'POST', {'json': {'instance': 'i'}}, 'copy_instance', 'instance_new', 201, 'instance_new', LEGACY),
    ('copy_instance_recursively/', 'POST', {'json': {'instance': 'i'}}, 'copy_instance_recursively', 'instance_new', 201, 'instance_new', LEGACY),
    ('infer_coupled_structure/', 'POST', {'json': {'coupled_system': 'i'}}, 'infer_coupled_system_structure', None, 201, '', LEGACY),
    ('get_instance_properties_recursively/', 'GET', {'query': {'instance': 'i'}}, 'get_instance_properties_recursively', {'label': 'x'}, 200, {'label': 'x'}, LEGACY),
    ('get_class_properties_recursively/', 'GET', {'query': {'class': 'solver'}}, 'get_class_properties_recursively', {'name': 'x'}, 200, {'name': 'x'}, LEGACY),
    ('get_class_hierarchy/', 'GET', {}, 'get_class_hierarchy', [{'name': 'solver'}], 200, [{'name': 'solver'}], LEGACY),
    ('get_class_instances/', 'GET', {'query': {'class': 'solver'}}, 'get_class_instances', ['i'], 200, ['i'], LEGACY),
    ('save_onto/', 'POST', {}, 'save_onto', None, 201, '', LEGACY),
    ('save_locally/', 'GET', {}, 'save_locally', None, None, None, LEGACY),
    ('download_owl/', 'GET', {}, 'save_locally', None, None, None, DOWNLOAD),
]

# Hand-validated parameters and their exact messages.
REQUIRED = [
    ('create_class_instance/', 'POST', {'json': {}}, 'class and label parameters are required'),
    ('replace_value/', 'POST', {'json': {}}, 'instance, property, old_value, and new_value parameters are required'),
    ('delete_value/', 'POST', {'json': {}}, 'instance, property, and value parameters are required'),
    ('delete_instance/', 'POST', {'json': {}}, 'instance parameter is required'),
    # Absent body: the same messages, not the generic validation text.
    ('create_class_instance/', 'POST', {}, 'class and label parameters are required'),
    ('replace_value/', 'POST', {}, 'instance, property, old_value, and new_value parameters are required'),
    ('delete_value/', 'POST', {}, 'instance, property, and value parameters are required'),
    ('delete_instance/', 'POST', {}, 'instance parameter is required'),
    ('get_class_metadata/', 'GET', {}, 'Missing required query parameter: class'),
    ('get_instance_property_metadata/', 'GET', {}, 'Missing required query parameter: instance'),
    ('get_value_deletion_preview/', 'GET', {}, 'Missing required query parameters: instance, property, target'),
    ('get_instance_deletion_preview/', 'GET', {}, 'Missing required query parameter: instance'),
]

# Type-checked parameters: status 400 and an error naming the parameter.
ILL_TYPED = [
    ('delete_value/', 'POST', {'json': {'instance': 'i', 'property': 'p', 'value': 1, 'cascade': 'yes'}}, 'cascade'),
    ('delete_instance/', 'POST', {'json': {'instance': 'i', 'cascade': 'yes'}}, 'cascade'),
    ('get_instance_deletion_preview/', 'GET', {'query': {'instance': 'i', 'cascade': 'maybe'}}, 'cascade'),
    ('search/', 'GET', {'query': {'q': 'x', 'limit': 'abc'}}, 'limit'),
]


def side_effect_patches(target):
    """No-op patches for the reload/persist calls, except when one of them is the route's own target."""
    return [patch(f'api.{name}') for name in SEMANTIC_SIDE_EFFECTS if name != target]


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
                for active in [patch(f'api.{target}', return_value=result)] + side_effect_patches(target):
                    stack.enter_context(active)
                got_status, got_body = call(self.client, method, path, request)
                self.assertEqual(got_status, status)
                self.assertEqual(got_body, body)

    def test_failure_status_and_error_body(self):
        for path, method, request, target, _, _, _, mapping in ROUTES:
            for failure, status in mapping.items():
                with self.subTest(path=path, failure=failure.__name__), ExitStack() as stack:
                    for active in [patch(f'api.{target}', side_effect=failure('boom'))] + side_effect_patches(target):
                        stack.enter_context(active)
                    got_status, got_body = call(self.client, method, path, request)
                    self.assertEqual(got_status, status)
                    self.assertEqual(got_body, {'error': 'boom'})

    def test_health_failure_bodies(self):
        for failure, status in ((GraphDBError, 503), (UnexpectedFailure, 500)):
            with self.subTest(failure=failure.__name__):
                with patch('api.get_graphdb_health', side_effect=failure('down')):
                    got_status, got_body = call(self.client, 'GET', 'health/', {})
                self.assertEqual(got_status, status)
                self.assertEqual(got_body['status'], 'error')
                self.assertEqual(got_body['graphdb'], 'unavailable')
                self.assertEqual(got_body['error'], 'down')
                self.assertIn('repository', got_body)

    def test_required_parameter_messages(self):
        for path, method, request, message in REQUIRED:
            with self.subTest(path=path):
                got_status, got_body = call(self.client, method, path, request)
                self.assertEqual(got_status, 400)
                self.assertEqual(got_body, {'error': message})

    def test_ill_typed_parameters(self):
        for path, method, request, parameter in ILL_TYPED:
            with self.subTest(path=path):
                got_status, got_body = call(self.client, method, path, request)
                self.assertEqual(got_status, 400)
                self.assertIn(parameter, got_body['error'])

    def test_cascade_defaults_to_true_and_false_is_forwarded(self):
        with patch('api.delete_instance_sparql', return_value={'instance': 'i', 'deleted': [], 'kept': [], 'unlinked_from': []}) as core:
            call(self.client, 'POST', 'delete_instance/', {'json': {'instance': 'i'}})
            core.assert_called_with('i', cascade=True)
            call(self.client, 'POST', 'delete_instance/', {'json': {'instance': 'i', 'cascade': False}})
            core.assert_called_with('i', cascade=False)
        with patch('api.get_instance_deletion_preview', return_value={}) as core:
            call(self.client, 'GET', 'get_instance_deletion_preview/', {'query': {'instance': 'i', 'cascade': 'false'}})
            core.assert_called_with('i', cascade=False)

    def test_depth_and_recursive_query_flags_are_forwarded(self):
        with patch('api.reload_ontology_from_graphdb'), \
                patch('api.get_instance_properties_recursively', return_value={}) as core:
            call(self.client, 'GET', 'get_instance_properties_recursively/', {'query': {'instance': 'i'}})
            core.assert_called_with('i', None, False)
            call(self.client, 'GET', 'get_instance_properties_recursively/', {'query': {'instance': 'i', 'depth': '2', 'recursive': 'True'}})
            core.assert_called_with('i', 2, True)
        with patch('api.reload_ontology_from_graphdb'), \
                patch('api.get_class_properties_recursively', return_value={}) as core:
            call(self.client, 'GET', 'get_class_properties_recursively/', {'query': {'class': 'c', 'depth': '3', 'recursive': 'True'}})
            core.assert_called_with('c', 3, True)

    def test_copy_body_flags_are_forwarded(self):
        with patch('api.reload_ontology_from_graphdb'), patch('api.save_onto'), \
                patch('api.copy_instance_recursively', return_value='instance_new') as core:
            call(self.client, 'POST', 'copy_instance_recursively/', {'json': {'instance': 'i', 'parent': 'p', 'data': {'a': 1}, 'depth': 2, 'recursive': 'True'}})
            core.assert_called_with('i', 'p', {'a': 1}, 2, True)
            call(self.client, 'POST', 'copy_instance_recursively/', {'json': {'instance': 'i'}})
            core.assert_called_with('i', None, None, None, False)

    def test_search_defaults(self):
        with patch('api.search_entities', return_value={'classes': [], 'instances': []}) as core:
            call(self.client, 'GET', 'search/', {'query': {'q': 'wing'}})
            args = core.call_args[0]
            self.assertEqual(args[:2], ('wing', 'all'))
            self.assertIsInstance(args[2], int)
            call(self.client, 'GET', 'search/', {'query': {'q': 'wing', 'type': 'classes', 'limit': '5'}})
            core.assert_called_with('wing', 'classes', 5)

    def test_head_and_malformed_json(self):
        with patch('api.get_graphdb_health', return_value={'status': 'ok'}):
            self.assertEqual(self.client.head(PREFIX + 'health/').status_code, 200)
        malformed = self.client.post(PREFIX + 'delete_instance/', content=b'{bad', headers={'Content-Type': 'application/json'})
        self.assertEqual(malformed.status_code, 400)
        self.assertTrue(malformed.json()['error'].startswith('request: '))

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
        listed = {PREFIX + path for path, *_ in ROUTES} | {PREFIX + 'health/', PREFIX + 'openapi.yaml', PREFIX + 'docs'}
        self.assertEqual({route.path for route in router.routes}, listed)

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
        with patch('api.add_values_sparql'):
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

        with patch('api.reload_ontology_from_graphdb'), patch('api.export_coupled_kratos', side_effect=slow_export):
            threads = [threading.Thread(target=call, args=(self.client, 'POST', 'export_coupled_kratos/', {'json': {'coupled_system': f'i{n}'}})) for n in range(3)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual(overlaps, [])


if __name__ == '__main__':
    unittest.main()
