import time
import os
import json
import logging

import pytest
import requests

from app.modules.graphdb_module import GraphDBModule

REPO = "test_repo_pytest"
log = logging.getLogger(__name__)


def _post_update(base_url: str, repo: str, update_str: str) -> requests.Response:
    """Attempts SPARQL UPDATE via multiple compatible paths, logging body on failure."""
    # Primary: POST /repositories/{repo} with application/sparql-update in querystring
    r = requests.post(
        f"{base_url}/repositories/{repo}",
        headers={"Content-Type": "application/sparql-update; charset=utf-8"},
        params={"update": update_str},
        timeout=10,
    )
    if r.status_code >= 400:
        print("GRAPHDB UPDATE primary error:", r.status_code, r.text)
    if r.ok:
        return r

    # Fallback 1: POST /repositories/{repo}/statements, form-encoded
    r = requests.post(
        f"{base_url}/repositories/{repo}/statements",
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
        data={"update": update_str},
        timeout=10,
    )
    if r.status_code >= 400:
        print("GRAPHDB UPDATE fallback1 error:", r.status_code, r.text)
    if r.ok:
        return r

    # Fallback 2: POST /repositories/{repo}/statements with raw SPARQL body
    r = requests.post(
        f"{base_url}/repositories/{repo}/statements",
        headers={"Content-Type": "application/sparql-update; charset=utf-8"},
        data=update_str,
        timeout=10,
    )
    if r.status_code >= 400:
        print("GRAPHDB UPDATE fallback2 error:", r.status_code, r.text)
    return r


@pytest.fixture(scope="session")
def graphdb_host_port(request):
    """Return host/port from env in CI; locally resolve via docker_services only if needed.

    We avoid referencing `docker_services` in the signature to not activate it in CI
    when DB_HOST_GRAPHDB/DB_PORT_GRAPHDB are already provided by the test-runner.
    """
    env_host = os.getenv("DB_HOST_GRAPHDB")
    env_port = os.getenv("DB_PORT_GRAPHDB")
    if env_host and env_port:
        try:
            return env_host, int(env_port)
        except ValueError:
            pass
    docker_services = request.getfixturevalue("docker_services")
    return "localhost", docker_services.port_for("graphdb", 7200)


@pytest.fixture(scope="session")
def base_url(graphdb_host_port):
    """Return GraphDB base URL using env or dynamic port."""
    host, port = graphdb_host_port
    return f"http://{host}:{port}"


def create_graphdb_repo(base_url: str, repo_id: str, title: str = "Test Repository"):
    """Create a GraphDB repository using a hardcoded Turtle config. Skip on failure."""
    # Wait for REST endpoint readiness
    for _ in range(60):
        try:
            r = requests.get(f"{base_url}/rest/repositories", timeout=3)
            if r.ok:
                break
        except requests.RequestException:
            time.sleep(1)
    else:
        pytest.skip("GraphDB not reachable")

    # Create if missing
    resp = requests.get(f"{base_url}/rest/repositories", timeout=10)
    resp.raise_for_status()
    if any(r.get("id") == repo_id for r in resp.json()):
        return

    # Attempt 1: JSON API (GraphDB vendor) to create a writable Free repo
    repo_payload = {
        "id": repo_id,
        "type": "free",
        "params": {
            "ruleset": "rdfsplus-optimized",
            "readOnly": False,
            "disableUpdate": False,
        },
    }
    try:
        # First try: vendor content-type
        r_create_json = requests.post(
            f"{base_url}/rest/repositories",
            headers={"Content-Type": "application/vnd.graphdb.repository+json"},
            data=json.dumps(repo_payload),
            timeout=30,
        )
        if not r_create_json.ok:
            print(
                "GraphDB repo JSON (vendor) failed:",
                r_create_json.status_code,
                r_create_json.text,
            )
            # Second try: application/json
            r_create_json = requests.post(
                f"{base_url}/rest/repositories",
                headers={"Content-Type": "application/json"},
                data=json.dumps(repo_payload),
                timeout=30,
            )
        if r_create_json.ok:
            time.sleep(5)
            return
        else:
            print(
                "GraphDB repo JSON (application/json) failed:",
                r_create_json.status_code,
                r_create_json.text,
            )
    except requests.RequestException as e:
        print("GraphDB repo JSON creation exception:", e)

    # Fallback: Turtle Free Sail (community compatibility)
    ttl = f'''@prefix rep:    <http://www.openrdf.org/config/repository#> .
@prefix sr:     <http://www.openrdf.org/config/repository/sail#> .
@prefix sail:   <http://www.openrdf.org/config/sail#> .
@prefix graphdb:<http://www.ontotext.com/config/graphdb#> .
@prefix rdfs:   <http://www.w3.org/2000/01/rdf-schema#> .

[] a rep:Repository ;
   rep:repositoryID "{repo_id}" ;
   rdfs:label "{title}" ;
   rep:repositoryImpl [ rep:repositoryType "graphdb:FreeSailRepository" ;
                        sr:sailImpl [ sail:sailType "graphdb:FreeSail" ;
                                      graphdb:ruleset "rdfsplus-optimized" ] ] .'''
    r_create = requests.post(
        f"{base_url}/rest/repositories",
        files={"config": ("config.ttl", ttl, "text/turtle")},
        timeout=30,
    )
    if not r_create.ok:
        body = r_create.text
        print(
            "\n--- GraphDB repo creation error body ---\n"
            + body
            + "\n--- end body ---\n"
        )
        pytest.skip(
            f"Repository creation error '{repo_id}': HTTP {r_create.status_code}. Body: {body}"
        )
    time.sleep(5)


@pytest.fixture(scope="session", autouse=True)
def ensure_repo(base_url):
    """Ensure the test repository exists."""
    create_graphdb_repo(base_url, REPO, title="Pytest repo")


@pytest.fixture
def mod(graphdb_host_port):
    """Create a GraphDBModule instance using env or a dynamic port."""
    host, port = graphdb_host_port
    return GraphDBModule(host=host, port=str(port))


@pytest.fixture
def sparql_headers():
    return {
        "update": {"Content-Type": "application/sparql-update"},
        "query": {"Accept": "application/sparql-results+json"},
    }


@pytest.fixture
def sample_triple():
    subj = "http://example.org/s"
    pred = "http://example.org/p"
    val = f"v_{int(time.time())}"
    lit = f'"{val}"'
    return subj, pred, lit


def test_list_repositories(mod, ensure_repo):
    """Verify the test repository is listed."""
    repos = mod.list_all_databases()
    assert REPO in repos, f"Repository '{REPO}' not found: {repos}"


def test_backup_creates_file(mod, tmp_path, base_url, sparql_headers, sample_triple):
    """Ensure backup_database produces a non-empty backup file."""
    subj, pred, lit = sample_triple
    q_insert = f"INSERT DATA {{ <{subj}> <{pred}> {lit} . }}"
    # Insert triple
    _post_update(base_url, REPO, q_insert).raise_for_status()
    # Backup
    backup_file = tmp_path / f"{REPO}.zip"
    success = mod.backup_database(REPO, backup_file)
    assert success, "backup_database returned False"
    assert backup_file.exists() and backup_file.stat().st_size > 0, (
        "Backup file missing or empty"
    )


def test_restore_recovers_data(mod, tmp_path, base_url, sparql_headers, sample_triple):
    """Ensure restore_database restores data from a backup."""
    subj, pred, lit = sample_triple
    q_insert = f"INSERT DATA {{ <{subj}> <{pred}> {lit} . }}"
    q_ask = f"ASK {{ <{subj}> <{pred}> {lit} . }}"
    q_delete = f"DELETE DATA {{ <{subj}> <{pred}> {lit} . }}"

    # Insert
    _post_update(base_url, REPO, q_insert).raise_for_status()
    # Backup
    backup_file = tmp_path / f"{REPO}.zip"
    assert mod.backup_database(REPO, backup_file)
    # Delete
    _post_update(base_url, REPO, q_delete).raise_for_status()
    # Verify deletion
    resp_del = requests.get(
        f"{base_url}/repositories/{REPO}",
        params={"query": q_ask},
        headers=sparql_headers["query"],
        timeout=10,
    )
    resp_del.raise_for_status()
    assert resp_del.json().get("boolean") is False, "Data still present after delete"
    # Restore
    assert mod.restore_database(REPO, backup_file), "restore_database returned False"
    time.sleep(2)
    # Verify restore
    resp_res = requests.get(
        f"{base_url}/repositories/{REPO}",
        params={"query": q_ask},
        headers=sparql_headers["query"],
        timeout=10,
    )
    resp_res.raise_for_status()
    assert resp_res.json().get("boolean") is True, "Data not found after restore"
