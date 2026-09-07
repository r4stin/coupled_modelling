import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

import importlib
import unittest
from unittest.mock import patch

import api
from fastapi.testclient import TestClient
from api import app

# A real, GraphDB-independent GET route: CORS headers must appear on actual API responses.
SPEC_ROUTE = '/api/v1.0/openapi.yaml'


class TestCorsHeaders(unittest.TestCase):
    """CORS headers for the separate Next.js frontend (offline — no GraphDB needed)."""

    def setUp(self):
        self.client = TestClient(app)
        self.allowed_origin = 'http://localhost:3000'

    def test_allowed_origin_gets_cors_headers(self):
        res = self.client.get(SPEC_ROUTE, headers={'Origin': self.allowed_origin})
        self.assertEqual(res.headers.get('Access-Control-Allow-Origin'), self.allowed_origin)
        self.assertIn('Origin', res.headers.get('Vary', ''))

    def test_preflight_options_gets_cors_headers(self):
        res = self.client.options(
            '/api/v1.0/add_values/',
            headers={
                'Origin': self.allowed_origin,
                'Access-Control-Request-Method': 'POST',
                'Access-Control-Request-Headers': 'Content-Type',
            })
        self.assertEqual(res.headers.get('Access-Control-Allow-Origin'), self.allowed_origin)
        self.assertEqual(res.headers.get('Access-Control-Max-Age'), '86400')
        self.assertIn('GET', res.headers.get('Access-Control-Allow-Methods', ''))
        self.assertIn('POST', res.headers.get('Access-Control-Allow-Methods', ''))
        self.assertIn('Content-Type', res.headers.get('Access-Control-Allow-Headers', ''))

    def test_disallowed_origin_gets_no_cors_headers(self):
        res = self.client.get(SPEC_ROUTE, headers={'Origin': 'http://evil.example.com'})
        self.assertIsNone(res.headers.get('Access-Control-Allow-Origin'))

    def test_no_origin_header_gets_no_cors_headers(self):
        res = self.client.get(SPEC_ROUTE)
        self.assertIsNone(res.headers.get('Access-Control-Allow-Origin'))

    def test_allowed_origins_configurable(self):
        """The origin list is read from the environment when the app is built."""
        try:
            with patch.dict(os.environ, {'CORS_ALLOWED_ORIGINS': 'https://kb.example.org'}):
                configured = importlib.reload(api)
            client = TestClient(configured.app)
            res = client.get(SPEC_ROUTE, headers={'Origin': 'https://kb.example.org'})
            self.assertEqual(res.headers.get('Access-Control-Allow-Origin'), 'https://kb.example.org')
            res = client.get(SPEC_ROUTE, headers={'Origin': self.allowed_origin})
            self.assertIsNone(res.headers.get('Access-Control-Allow-Origin'))
        finally:
            importlib.reload(api)


if __name__ == '__main__':
    unittest.main()
