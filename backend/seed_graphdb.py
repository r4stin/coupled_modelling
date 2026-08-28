"""GraphDB bootstrap for the containerized stack: waits for the server, creates
the repository when missing, and seeds the application's named graph from the
bundled onto.owl when that graph is empty. Runs before the API starts.
"""
import os
import sys
import time

import requests

READINESS_ATTEMPTS = 60


def wait_for_graphdb(url):
    for _ in range(READINESS_ATTEMPTS):
        try:
            # Any well-formed response (401 included) proves the server is up.
            if requests.get(f'{url}/rest/repositories', timeout=5).status_code < 500:
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    sys.exit(f'GraphDB at {url} did not become ready in time.')


# Importing `main` performs GraphDB requests at module level, so the readiness
# wait must come first; config is then read from `main` to keep one source.
wait_for_graphdb(os.getenv('GRAPHDB_URL', 'http://localhost:7200'))

import main  # noqa: E402

REPO_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'docker', 'graphdb-repo-config.ttl')


def ensure_repository():
    probe = requests.get(f'{main.GRAPHDB_URL}/repositories/{main.REPOSITORY}/size', auth=main.get_graphdb_auth(), timeout=30)
    if probe.ok:
        return
    if probe.status_code != 404:
        sys.exit(f'Probing GraphDB repository {main.REPOSITORY} failed: {probe.status_code} {probe.text}')
    with open(REPO_CONFIG_PATH, encoding='utf-8') as config_file:
        config = config_file.read().replace('"coupled_modelling"', f'"{main.REPOSITORY}"')
    created = requests.post(
        f'{main.GRAPHDB_URL}/rest/repositories',
        files={'config': ('repo-config.ttl', config)},
        auth=main.get_graphdb_auth(),
        timeout=30,
    )
    if not created.ok:
        sys.exit(f'Creating GraphDB repository {main.REPOSITORY} failed: {created.status_code} {created.text}')
    print(f'Created GraphDB repository {main.REPOSITORY}.')


def graph_has_data():
    # Graph-scoped and namespace-filtered: a fresh repository already holds
    # ruleset axioms, and an interrupted seed leaves non-canonical IRIs —
    # both must read as "no data" so seeding (re)runs.
    query = f'ASK {{ GRAPH <{main.onto_uri}> {{ ?s ?p ?o . FILTER(STRSTARTS(STR(?s), "{main.onto_uri}#")) }} }}'
    return main.query_graphdb(query).get('boolean', False)


ensure_repository()
if graph_has_data():
    print('GraphDB repository already has data; skipping seed.')
else:
    main.save_onto()
    # save_onto only logs push failures; verify the graph holds the seed.
    if not graph_has_data():
        sys.exit('Seeding GraphDB from onto.owl failed — see the log above.')
    print('Seeded the empty GraphDB repository from onto.owl.')
