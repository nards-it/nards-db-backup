import json
import logging
import os
import time

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


def test_restore_replaces_data_and_preserves_named_graph(mod, tmp_path, base_url):
    graph = "http://example.org/backup-test-graph"
    before = "http://example.org/before"
    after = "http://example.org/after"
    _post_update(
        base_url,
        REPO,
        f'INSERT DATA {{ GRAPH <{graph}> {{ <{before}> <http://example.org/p> "saved" }} }}',
    ).raise_for_status()
    backup = tmp_path / "repo.backup"
    assert mod.backup_database(REPO, backup)
    _post_update(
        base_url,
        REPO,
        f'DELETE DATA {{ GRAPH <{graph}> {{ <{before}> <http://example.org/p> "saved" }} }}; '
        f'INSERT DATA {{ <{after}> <http://example.org/p> "new" }}',
    ).raise_for_status()
    assert mod.restore_database(REPO, backup)
    for query, expected in [
        (
            f'ASK {{ GRAPH <{graph}> {{ <{before}> <http://example.org/p> "saved" }} }}',
            True,
        ),
        (f'ASK {{ <{after}> <http://example.org/p> "new" }}', False),
    ]:
        response = requests.get(
            f"{base_url}/repositories/{REPO}",
            params={"query": query},
            headers={"Accept": "application/sparql-results+json"},
            timeout=10,
        )
        response.raise_for_status()
        assert response.json()["boolean"] is expected


def test_corrupt_restore_keeps_existing_data(mod, tmp_path, base_url):
    marker = "http://example.org/rollback-marker"
    _post_update(
        base_url, REPO, f'INSERT DATA {{ <{marker}> <http://example.org/p> "keep" }}'
    ).raise_for_status()
    backup = tmp_path / "broken.backup"
    backup.write_text("not valid RDF")

    assert not mod.restore_database(REPO, backup)
    response = requests.get(
        f"{base_url}/repositories/{REPO}",
        params={"query": f'ASK {{ <{marker}> <http://example.org/p> "keep" }}'},
        headers={"Accept": "application/sparql-results+json"},
        timeout=10,
    )
    response.raise_for_status()
    assert response.json()["boolean"] is True


def test_restore_exactly_matches_backup_after_data_changes(mod, tmp_path, base_url):
    _post_update(base_url, REPO, "CLEAR ALL").raise_for_status()
    _post_update(
        base_url,
        REPO,
        """INSERT DATA {
            <urn:common> <urn:predicate> "common" .
            <urn:removed> <urn:predicate> "restore me" .
            GRAPH <urn:saved-graph> { <urn:saved> <urn:predicate> "saved" . }
        }""",
    ).raise_for_status()
    backup = tmp_path / "snapshot.backup"
    assert mod.backup_database(REPO, backup)
    expected = set(backup.read_text().splitlines())

    _post_update(
        base_url,
        REPO,
        """DELETE DATA {
            <urn:removed> <urn:predicate> "restore me" .
            GRAPH <urn:saved-graph> { <urn:saved> <urn:predicate> "saved" . }
        }; INSERT DATA {
            <urn:extra> <urn:predicate> "remove me" .
            GRAPH <urn:extra-graph> { <urn:extra> <urn:predicate> "remove me" . }
        }""",
    ).raise_for_status()
    assert mod.restore_database(REPO, backup)

    response = requests.get(
        f"{base_url}/repositories/{REPO}/statements",
        params={"infer": "false"},
        headers={"Accept": "application/n-quads"},
        timeout=10,
    )
    response.raise_for_status()
    assert set(response.text.splitlines()) == expected


def test_restore_replaces_blank_nodes_and_preserves_links(mod, tmp_path, base_url):
    _post_update(base_url, REPO, "CLEAR ALL").raise_for_status()
    _post_update(
        base_url,
        REPO,
        'INSERT DATA { _:extra <urn:predicate> "keep if restore fails" . }',
    ).raise_for_status()
    backup = tmp_path / "snapshot.backup"
    backup.write_text(
        '_:saved <urn:predicate> "saved" .\n'
        '_:saved <urn:predicate> "named" <urn:graph> .\n'
    )
    for _ in range(2):
        assert mod.restore_database(REPO, backup)

    response = requests.get(
        f"{base_url}/repositories/{REPO}",
        params={
            "query": 'ASK { ?s <urn:predicate> "saved" . '
            'GRAPH <urn:graph> { ?s <urn:predicate> "named" } }'
        },
        headers={"Accept": "application/sparql-results+json"},
        timeout=10,
    )
    response.raise_for_status()
    assert response.json()["boolean"] is True
    response = requests.get(
        f"{base_url}/repositories/{REPO}",
        params={"query": 'ASK { ?s <urn:predicate> "keep if restore fails" }'},
        headers={"Accept": "application/sparql-results+json"},
        timeout=10,
    )
    response.raise_for_status()
    assert response.json()["boolean"] is False


def test_corrupt_restore_recovers_blank_nodes(mod, tmp_path, base_url):
    _post_update(base_url, REPO, "CLEAR ALL").raise_for_status()
    _post_update(
        base_url,
        REPO,
        'INSERT DATA { _:s <urn:p> "before" . GRAPH <urn:g> { _:s <urn:p> "linked" } }',
    ).raise_for_status()
    backup = tmp_path / "corrupt.backup"
    backup.write_text("not valid RDF")

    assert not mod.restore_database(REPO, backup)
    response = requests.get(
        f"{base_url}/repositories/{REPO}",
        params={
            "query": 'ASK { ?s <urn:p> "before" . GRAPH <urn:g> { ?s <urn:p> "linked" } }'
        },
        headers={"Accept": "application/sparql-results+json"},
        timeout=10,
    )
    response.raise_for_status()
    assert response.json()["boolean"] is True
    assert not list(tmp_path.glob(".graphdb-recovery-*"))


def test_failed_recovery_retains_snapshot(mod, tmp_path, base_url, monkeypatch):
    _post_update(base_url, REPO, "CLEAR ALL").raise_for_status()
    _post_update(
        base_url, REPO, 'INSERT DATA { <urn:old> <urn:p> "old" }'
    ).raise_for_status()
    backup = tmp_path / "backup.nq"
    backup.write_text('<urn:new> <urn:p> "new" .\n')

    original_post = mod._post
    calls = []

    def fail_import(path, **kwargs):
        calls.append(path)
        if "headers" in kwargs:
            raise requests.ConnectionError("simulated import failure")
        return original_post(path, **kwargs)

    monkeypatch.setattr(mod, "_post", fail_import)
    assert not mod.restore_database(REPO, backup)
    assert len(calls) == 4
    snapshots = list(tmp_path.glob(".graphdb-recovery-*/previous.nq"))
    assert len(snapshots) == 1
    assert '<urn:old> <urn:p> "old" .' in snapshots[0].read_text()
    assert (
        json.loads((snapshots[0].parent / "metadata.json").read_text())["repository"]
        == REPO
    )


def test_interruption_preserves_recovery_snapshot(mod, tmp_path, monkeypatch):
    backup = tmp_path / "backup.nq"
    backup.write_text('<urn:new> <urn:p> "new" .\n')

    def interrupt(name, path):
        raise KeyboardInterrupt()

    monkeypatch.setattr(mod, "_replace_rdf", interrupt)
    with pytest.raises(KeyboardInterrupt):
        mod.restore_database(REPO, backup)
    assert len(list(tmp_path.glob(".graphdb-recovery-*/previous.nq"))) == 1


def test_restore_into_empty_repository(mod, tmp_path, base_url):
    _post_update(base_url, REPO, "CLEAR ALL").raise_for_status()
    backup = tmp_path / "valid.backup"
    backup.write_text('<http://example.org/s> <http://example.org/p> "value" .\n')

    assert mod.restore_database(REPO, backup)
    response = requests.get(
        f"{base_url}/repositories/{REPO}",
        params={
            "query": 'ASK { <http://example.org/s> <http://example.org/p> "value" }'
        },
        headers={"Accept": "application/sparql-results+json"},
        timeout=10,
    )
    response.raise_for_status()
    assert response.json()["boolean"] is True
