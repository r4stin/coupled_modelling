"""The API routers, one per tag, in the order the OpenAPI document lists their operations."""
from . import explorer, files, legacy, mutations, semantic, system

ROUTERS = (system.router, explorer.router, mutations.router, semantic.router, files.router, legacy.router)
