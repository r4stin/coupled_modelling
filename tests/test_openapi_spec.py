import os
import sys
import unittest

import yaml
from fastapi.testclient import TestClient

# Adjust paths to import from backend/
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))

from api import app, router

SPEC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'openapi.yaml')
API_PREFIX = '/api/v1.0'

# Schema names the frontend's generated types are built from.
FRONTEND_SCHEMAS = [
    'Error', 'ScalarValue', 'HealthOk', 'HealthError', 'ClassHierarchyEntry', 'InstanceSummary', 'PreviewItem',
    'ClassMetadata', 'Restriction', 'NamedReference', 'InstanceMetadata', 'InstancePropertyGroup',
    'ObjectPropertyValue', 'LiteralPropertyValue', 'ObjectValueTarget', 'LiteralValueTarget', 'DeletionPreview',
    'UnlinkResult', 'InstanceId', 'PropertyDataMap', 'KratosParameters', 'SearchResults', 'SearchClassResult',
]
FRONTEND_OPERATIONS = ['deleteInstance', 'deleteValue', 'searchEntities']


class TestOpenAPISpec(unittest.TestCase):
    """The committed openapi.yaml is the document generated from the routes; the two must never drift."""

    @classmethod
    def setUpClass(cls):
        cls.generated = app.openapi()
        with open(SPEC_PATH, encoding='utf-8') as spec_file:
            cls.committed = yaml.safe_load(spec_file)

    def test_committed_document_equals_the_generated_one(self):
        self.assertEqual(self.committed, self.generated, 'openapi.yaml is stale: run `python backend/export_openapi.py`')

    def test_served_document_equals_the_generated_one(self):
        response = TestClient(app).get(f'{API_PREFIX}/openapi.yaml')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers['content-type'].startswith('application/yaml'))
        self.assertEqual(yaml.safe_load(response.text), self.generated)

    def test_every_documented_route_is_registered_and_vice_versa(self):
        registered = {(route.path, method) for route in router.routes if route.include_in_schema for method in route.methods}
        documented = {(path, method.upper()) for path, item in self.generated['paths'].items() for method in item}
        self.assertEqual(documented, registered)

    def test_paths_carry_the_prefix_and_the_server_does_not(self):
        self.assertTrue(all(path.startswith(API_PREFIX) for path in self.generated['paths']))
        self.assertEqual([server['url'] for server in self.generated['servers']], ['http://localhost:5000'])

    def test_no_validation_error_responses_the_app_never_emits(self):
        for path, item in self.generated['paths'].items():
            for method, operation in item.items():
                self.assertNotIn('422', operation['responses'], f'{method.upper()} {path}')
                self.assertIn('operationId', operation, f'{method.upper()} {path}')
        self.assertNotIn('HTTPValidationError', self.generated['components']['schemas'])

    def test_every_error_response_is_json(self):
        for path, item in self.generated['paths'].items():
            for method, operation in item.items():
                for status, response in operation['responses'].items():
                    if status.startswith(('4', '5')):
                        self.assertEqual(list(response['content']), ['application/json'], f'{method.upper()} {path} {status}')

    def test_frontend_contract_names_exist(self):
        schemas = self.generated['components']['schemas']
        self.assertEqual([name for name in FRONTEND_SCHEMAS if name not in schemas], [])
        operation_ids = {operation['operationId'] for item in self.generated['paths'].values() for operation in item.values()}
        self.assertEqual([name for name in FRONTEND_OPERATIONS if name not in operation_ids], [])
        values = schemas['InstancePropertyGroup']['properties']['values']['items']
        self.assertEqual(values['discriminator']['mapping']['literal'], '#/components/schemas/LiteralPropertyValue')


if __name__ == '__main__':
    unittest.main()
