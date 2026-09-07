# GraphDB Migration Quickstart

Follow these steps to set up the GraphDB-backed REST API and verify the integration workflows.

---

## 0. One-Command Stack (Docker)

The whole stack — GraphDB, this backend, and the [React explorer](https://github.com/r4stin/coupled-modelling-frontend) — can run with Docker instead of the manual setup below. Clone the frontend repo **as a sibling directory** of this one, then from this repo:

```bash
docker compose up --build
```

Open the explorer at `http://localhost:3000` (backend API health check: `http://localhost:5000/api/v1.0/health/`, GraphDB Workbench: `http://localhost:7200`; the backend serves no page at its root URL). On first start the repository is created automatically (from `docker/graphdb-repo-config.ttl` — same defaults as the manual setup in §1) and seeded from `backend/onto.owl`; data persists in a named Docker volume (`docker compose down -v` resets it). Host ports are overridable via `GRAPHDB_PORT`, `BACKEND_PORT`, and `FRONTEND_PORT` (see the notes in `docker-compose.yml`). The Docker setup targets local use; the development workflows below (§5 demos, §6 test suite) use the manual setup.

---

## 1. Database Setup
1. Download and run [GraphDB](https://graphdb.ontotext.com/) locally (default URL is `http://localhost:7200`).
2. Open the GraphDB Workbench in your browser, go to **Setup** -> **Repositories** -> **Create new repository**.
3. Create a repository with **Repository ID** set to `coupled_modelling` (use default settings for the rest).

---

## 2. Configuration & Environment Variables
The application automatically configures itself, but you can override connection settings via the following environment variables:
* `GRAPHDB_URL` (default: `http://localhost:7200`) — The URL of the GraphDB server instance.
* `GRAPHDB_REPOSITORY` (default: `coupled_modelling`) — The active repository ID.
* `GRAPHDB_USER` / `GRAPHDB_PASSWORD` — Credentials to authenticate against GraphDB (if basic authentication is enabled).

---

## 3. Installation & Running
1. Install Python dependencies:
   ```bash
   pip install -r backend/requirements.txt
   pip install -r coupled_modelling/requirements.txt
   pip install -e .
   ```
2. Start the API server (uvicorn):
   ```bash
   python backend/api.py
   ```
   For development with auto-reload on file changes:
   ```bash
   cd backend && uvicorn api:app --reload --port 5000
   ```

---

## 4. Web Explorer (separate repository)

The web explorer and editor UI lives in its own repository, [coupled-modelling-frontend](https://github.com/r4stin/coupled-modelling-frontend), and talks to this backend exclusively through the HTTP API. This service itself serves no user interface.

To use the explorer, either start the full Docker stack (§0) and open `http://localhost:3000`, or run the frontend from its repository (`npm run dev`) against a locally running API server; setup details are in that repository's README.

---

## 5. Initializing the Database & Running Demos

Once the API server is active, populate the database with the core ontology schema and co-simulation instances:

1. **Populate the Database:**
   ```bash
   python backend/test.py
   ```
   *(This loads the base co-simulation schema, creates the initial solvers and criteria, and writes the reference ontology file `examples/test.owl`)*

2. **Verify with the Workflow Demo:**
   ```bash
   python examples/demo_api.py
   ```
   *(This validates the client API interactions by building and exporting a complete co-simulation setup to `examples/export_onera_fsi.json`)*

---

## 6. Running the Test Suite

After the database has been initialized with the base schema, you can run the test suite to verify the integrity of the RDF serialization, SPARQL update pathways, and web endpoints. 

To run the tests without namespace shadowing conflicts (e.g., from other global test libraries), run the following command:

```bash
PYTHONPATH=. python -m unittest discover -s tests -p "test_*.py" -v
```

The SPARQL integration tests require a running GraphDB instance and modify repository data. Use a dedicated test repository where possible.

### Purpose of the Tests:
* `test_serialization.py`: Validates SPARQL/RDF term serialization and local resource name validation.
* `test_sparql_mutations.py`: Tests the execution of SPARQL-based updates (inserting, deleting, and replacing properties on existing subjects).
* `test_sparql_creation.py`: Tests direct instance instantiation, class validation against GraphDB, and safe prefix-isolated test teardowns.
* `test_explorer_api.py`: Tests the explorer-facing API — routing contracts, health error mapping (503/400), tree inheritance parsing, and global search.
* `test_api_contract.py`: Pins the HTTP contract route by route — status code per failure class, required-parameter messages, empty-body creations, flag forwarding, slash redirect, and the one-at-a-time rule for the Owlready2 routes.
* `test_web_mutations.py`: Tests web mutation endpoints (`/delete_value/`, `/create_class_instance/`, `/download_owl/`, `/delete_instance/`, the two deletion previews), the individual-only existence rule, boolean string parsing safety, and GraphDB error codes.
* `test_cors.py`: Tests the CORS headers exposed for the separate Next.js frontend (`CORS_ALLOWED_ORIGINS`).
* `test_openapi_spec.py`: Verifies `openapi.yaml` stays in sync with the registered routes (every route documented, no stale operations).

---

## 7. Architecture: Hybrid Owlready2 + GraphDB
* **Direct SPARQL mutations:** Simple value insertions, deletions, replacements, instance creation (UUID-based), and instance deletion (cascading over the instance's owned subtree, keeping anything still linked from elsewhere) run directly in GraphDB via transactional SPARQL Update requests.
* **In-memory Owlready2 workflows:** Copy operations, complex ontology construction, KRATOS JSON import/export, and structural inference continue to use Owlready2 and synchronize with GraphDB.

---

## 8. API Reference (OpenAPI)

The REST API is documented by [`openapi.yaml`](openapi.yaml) (OpenAPI 3.1), generated from the route declarations in `backend/api.py` and the models in `backend/schemas.py`: every endpoint under `/api/v1.0/` with request/response schemas, error contracts (`400`/`503`/`500`), and which architecture path (direct SPARQL vs. in-memory Owlready2) serves it.

* **Served by the API itself:** the running backend exposes the document at `http://localhost:5000/api/v1.0/openapi.yaml` (JSON at `/api/v1.0/openapi.json`) and renders it as interactive documentation at `http://localhost:5000/api/v1.0/docs`.
* **Regenerate after a route or model change:** `python backend/export_openapi.py` rewrites `openapi.yaml`; `tests/test_openapi_spec.py` fails CI whenever the committed file differs from the generated document.
* **Generate a typed client:** the Next.js frontend generates its TypeScript API types from the served document (`npm run generate:api-types` in the frontend repo, using `openapi-typescript`).
