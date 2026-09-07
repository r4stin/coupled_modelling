import os
import re
import sys
import unittest

# Adjust paths to import from backend/
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))

from fastapi.testclient import TestClient
from api import app, router

SPEC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'openapi.yaml')
API_PREFIX = '/api/v1.0'
HTTP_METHODS = {'get', 'post', 'put', 'patch', 'delete', 'options', 'head'}


def parse_spec_operations(spec_text):
    """
    Extracts {(path, METHOD)} pairs from the paths section of openapi.yaml
    using indentation only, so no YAML library is required.
    """
    operations = set()
    in_paths = False
    current_path = None
    for line in spec_text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if indent == 0:
            in_paths = (stripped == 'paths:')
            current_path = None
            continue
        if not in_paths:
            continue
        if indent == 2 and stripped.startswith('/') and stripped.endswith(':'):
            current_path = stripped[:-1]
        elif indent == 4 and current_path and stripped.rstrip(':') in HTTP_METHODS:
            operations.add((current_path, stripped.rstrip(':').upper()))
    return operations


class TestOpenAPISpecCoverage(unittest.TestCase):
    """Verifies openapi.yaml stays in sync with the routes in backend/api.py."""

    @classmethod
    def setUpClass(cls):
        with open(SPEC_PATH, encoding='utf-8') as f:
            cls.spec_text = f.read()
        cls.spec_operations = parse_spec_operations(cls.spec_text)

    def get_app_operations(self):
        """(path, METHOD) pairs of every route registered on the API router."""
        operations = set()
        for route in router.routes:
            if not route.path.startswith(API_PREFIX) or not route.include_in_schema:
                continue
            for method in route.methods - {'OPTIONS', 'HEAD'}:
                operations.add((route.path[len(API_PREFIX):], method))
        return operations

    def test_spec_parses_and_has_operations(self):
        """The paths section parses and documents a plausible number of operations."""
        self.assertIn('openapi:', self.spec_text)
        self.assertGreaterEqual(len(self.spec_operations), 20)

    def test_every_app_route_is_documented(self):
        """Every /api/v1.0/ route the app registers appears in openapi.yaml."""
        missing = self.get_app_operations() - self.spec_operations
        self.assertEqual(
            missing, set(),
            f"Routes missing from openapi.yaml: {sorted(missing)}"
        )

    def test_every_documented_path_exists_in_app(self):
        """openapi.yaml documents no operation that the app does not serve."""
        stale = self.spec_operations - self.get_app_operations()
        self.assertEqual(
            stale, set(),
            f"openapi.yaml operations with no matching route: {sorted(stale)}"
        )

    def test_spec_endpoint_serves_the_file(self):
        """GET /api/v1.0/openapi.yaml serves the specification document."""
        client = TestClient(app)
        response = client.get('/api/v1.0/openapi.yaml')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.text.startswith('openapi:'))

    def test_server_url_matches_api_prefix(self):
        """The spec's server URL carries the /api/v1.0 prefix the routes omit."""
        match = re.search(r'^\s*-\s*url:\s*(\S+)', self.spec_text, re.MULTILINE)
        self.assertIsNotNone(match, "No server url found in openapi.yaml")
        self.assertTrue(match.group(1).endswith(API_PREFIX))


if __name__ == '__main__':
    unittest.main()
