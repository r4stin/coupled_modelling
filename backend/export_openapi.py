"""Writes the OpenAPI document generated from the routes to the repository's openapi.yaml."""
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
SPEC_PATH = os.path.join(BACKEND_DIR, '..', 'openapi.yaml')
sys.path.insert(0, BACKEND_DIR)

from api import app  # noqa: E402
from routing import openapi_yaml  # noqa: E402

with open(SPEC_PATH, 'w', encoding='utf-8') as spec_file:
    spec_file.write(openapi_yaml(app))
print(f'Wrote {os.path.abspath(SPEC_PATH)}')
