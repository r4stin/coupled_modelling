import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

import unittest

import api
from api import app


class TestCorsHeaders(unittest.TestCase):
    """CORS headers for the separate Next.js frontend (offline — no GraphDB needed)."""

    def setUp(self):
        self.client = app.test_client()
        self.allowed_origin = 'http://localhost:3000'

    def test_allowed_origin_gets_cors_headers(self):
        res = self.client.get('/', headers={'Origin': self.allowed_origin})
        self.assertEqual(res.headers.get('Access-Control-Allow-Origin'), self.allowed_origin)
        self.assertIn('GET', res.headers.get('Access-Control-Allow-Methods', ''))
        self.assertIn('POST', res.headers.get('Access-Control-Allow-Methods', ''))
        self.assertEqual(res.headers.get('Access-Control-Allow-Headers'), 'Content-Type')
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

    def test_disallowed_origin_gets_no_cors_headers(self):
        res = self.client.get('/', headers={'Origin': 'http://evil.example.com'})
        self.assertIsNone(res.headers.get('Access-Control-Allow-Origin'))

    def test_no_origin_header_gets_no_cors_headers(self):
        res = self.client.get('/')
        self.assertIsNone(res.headers.get('Access-Control-Allow-Origin'))

    def test_allowed_origins_configurable(self):
        original = api.CORS_ALLOWED_ORIGINS
        try:
            api.CORS_ALLOWED_ORIGINS = ['https://kb.example.org']
            res = self.client.get('/', headers={'Origin': 'https://kb.example.org'})
            self.assertEqual(res.headers.get('Access-Control-Allow-Origin'), 'https://kb.example.org')
            res = self.client.get('/', headers={'Origin': self.allowed_origin})
            self.assertIsNone(res.headers.get('Access-Control-Allow-Origin'))
        finally:
            api.CORS_ALLOWED_ORIGINS = original


if __name__ == '__main__':
    unittest.main()
