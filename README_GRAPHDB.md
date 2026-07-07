# GraphDB Migration Quickstart

Follow these steps to set up the GraphDB-backed REST API and verify the integration workflows.

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
2. Start the local Flask API server:
   ```bash
   python backend/api.py
   ```

---

## 4. Initializing the Database & Running Demos

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

## 5. Running the Test Suite

After the database has been initialized with the base schema, you can run the test suite to verify the integrity of the RDF serialization and SPARQL update pathways. 

To run the tests without namespace shadowing conflicts (e.g., from other global test libraries), run the following command:

```bash
python -m unittest tests/test_serialization.py tests/test_sparql_mutations.py tests/test_sparql_creation.py -v
```

The SPARQL integration tests require a running GraphDB instance and modify repository data. Use a dedicated test repository where possible.

### Purpose of the Tests:
* `test_serialization.py`: Validates SPARQL/RDF term serialization and local resource name validation.
* `test_sparql_mutations.py`: Tests the execution of SPARQL-based updates (inserting, deleting, and replacing properties on existing subjects).
* `test_sparql_creation.py`: Tests direct instance instantiation, class validation against GraphDB, and safe prefix-isolated test teardowns.

---

## 6. Architecture: Hybrid Owlready2 + GraphDB
* **Direct SPARQL mutations:** Simple value insertions, deletions, replacements, and instance creation using collision-resistant UUIDs run directly in GraphDB through SPARQL Update requests.
* **In-memory Owlready2 workflows:** Copy operations, ontology construction, KRATOS import, and structural inference continue to use Owlready2 and synchronize the resulting ontology with GraphDB.
