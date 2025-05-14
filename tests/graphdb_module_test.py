import time
import logging
from pathlib import Path

import pytest
import requests

from app.modules.graphdb_module import GraphDBModule

REPO = "test_repo_pytest"
log = logging.getLogger(__name__)

@pytest.fixture(scope="session")
def graphdb_port(docker_services):
    """Ritorna la porta assegnata dinamicamente al servizio graphdb."""
    return docker_services.port_for("graphdb", 7200)

@pytest.fixture(scope="session")
def base_url(graphdb_port):
    """Ritorna la URL di base per GraphDB usando la porta dinamica."""
    return f"http://localhost:{graphdb_port}"

# Helper per creazione repository via GraphDB REST
def create_graphdb_repo(base_url: str, repo_id: str, title: str = "Test Repository"):
    """
    Crea un repository in GraphDB usando config Turtle hardcoded. Skip se errore.
    """
    # Attendi endpoint
    for _ in range(60):
        try:
            r = requests.get(f"{base_url}/rest/repositories", timeout=3)
            if r.ok:
                break
        except requests.RequestException:
            time.sleep(1)
    else:
        pytest.skip("GraphDB non raggiungibile")

    # Crea se non esiste
    resp = requests.get(f"{base_url}/rest/repositories", timeout=10)
    resp.raise_for_status()
    if any(r.get("id") == repo_id for r in resp.json()):
        return

    ttl = f'''@prefix rep: <http://www.openrdf.org/config/repository#> .
@prefix sr: <http://www.openrdf.org/config/repository/sail#> .
@prefix sail: <http://www.openrdf.org/config/sail#> .
@prefix grdb: <http://www.ontotext.com/config/graphdb#> .

[] a rep:Repository ;
   rep:repositoryID "{repo_id}" ;
   rep:repositoryTitle "{title}" ;
   rep:repositoryImpl [ rep:repositoryType "graphdb:FreeSailRepository" ;
                       sr:sailImpl [ sail:sailType "graphdb:FreeSail" ;
                                     grdb:ruleset "owl-horst-optimized" ] ] .'''
    r_create = requests.post(
        f"{base_url}/rest/repositories",
        files={"config": ("config.ttl", ttl, "text/turtle")},
        timeout=30
    )
    try:
        r_create.raise_for_status()
    except requests.RequestException as e:
        pytest.skip(f"Errore creazione repo '{repo_id}': {e}")
    time.sleep(5)

@pytest.fixture(scope="session", autouse=True)
def ensure_repo(base_url):
    """Assicura esistenza repo di test."""
    create_graphdb_repo(base_url, REPO, title="Pytest repo")

@pytest.fixture
def mod(graphdb_port):
    """Istanza di GraphDBModule con porta dinamica."""
    return GraphDBModule(host="localhost", port=str(graphdb_port))

@pytest.fixture
def sparql_headers():
    return {
        "update": {"Content-Type": "application/sparql-update"},
        "query":  {"Accept": "application/sparql-results+json"}
    }

@pytest.fixture
def sample_triple():
    subj = "http://example.org/s"
    pred = "http://example.org/p"
    val  = f"v_{int(time.time())}"
    lit  = f'"{val}"'
    return subj, pred, lit


def test_list_repositories(mod, ensure_repo):
    """Verifica che il repository di test sia elencato."""
    repos = mod.list_all_databases()
    assert REPO in repos, f"Repository '{REPO}' non trovato: {repos}"


def test_backup_creates_file(mod, tmp_path, base_url, sparql_headers, sample_triple):
    """Test che backup_database produce un file ZIP non vuoto."""
    subj, pred, lit = sample_triple
    q_insert = f"INSERT DATA {{ <{subj}> <{pred}> {lit} . }}"
    # Inserisco triple
    requests.post(
        f"{base_url}/repositories/{REPO}/statements",
        data=q_insert, headers=sparql_headers["update"], timeout=10
    ).raise_for_status()
    # Backup
    backup_file = tmp_path / f"{REPO}.zip"
    success = mod.backup_database(REPO, backup_file)
    assert success, "backup_database ha restituito False"
    assert backup_file.exists() and backup_file.stat().st_size > 0, "Backup file non creato o vuoto"


def test_restore_recovers_data(mod, tmp_path, base_url, sparql_headers, sample_triple):
    """Test che restore_database ripristina i dati di un backup."""
    subj, pred, lit = sample_triple
    q_insert = f"INSERT DATA {{ <{subj}> <{pred}> {lit} . }}"
    q_ask    = f"ASK {{ <{subj}> <{pred}> {lit} . }}"
    q_delete = f"DELETE DATA {{ <{subj}> <{pred}> {lit} . }}"

    # Inserisco
    requests.post(
        f"{base_url}/repositories/{REPO}/statements",
        data=q_insert, headers=sparql_headers["update"], timeout=10
    ).raise_for_status()
    # Backup
    backup_file = tmp_path / f"{REPO}.zip"
    assert mod.backup_database(REPO, backup_file)
    # Cancello
    requests.post(
        f"{base_url}/repositories/{REPO}/statements",
        data=q_delete, headers=sparql_headers["update"], timeout=10
    ).raise_for_status()
    # Verifico cancellazione
    resp_del = requests.get(
        f"{base_url}/repositories/{REPO}",
        params={"query": q_ask}, headers=sparql_headers["query"], timeout=10
    )
    resp_del.raise_for_status()
    assert resp_del.json().get("boolean") is False, "Dati ancora presenti dopo delete"
    # Ripristino
    assert mod.restore_database(REPO, backup_file), "restore_database ha restituito False"
    time.sleep(2)
    # Verifico restore
    resp_res = requests.get(
        f"{base_url}/repositories/{REPO}",
        params={"query": q_ask}, headers=sparql_headers["query"], timeout=10
    )
    resp_res.raise_for_status()
    assert resp_res.json().get("boolean") is True, "Dati non trovati dopo restore"
