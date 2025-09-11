import os
import sys
import time
from pathlib import Path

import psycopg2
import pytest

from app.modules.postgis_module import PostGISModule

# insert root directory into python module search path
sys.path.insert(1, os.getcwd())


def _pg_ready(host: str, port: int, user: str, password: str, dbname: str) -> bool:
    try:
        conn = psycopg2.connect(
            host=host, port=port, user=user, password=password, dbname=dbname
        )
        conn.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session", autouse=True)
def postgis_vector_service(request):
    """Ensure the PostGIS (with pgvector package available) is reachable.

    In CI: env vars DB_*_POSTGIS_VECTOR are provided by test-runner to target the
    'postgis_vector' service.
    In local venv: use pytest-docker's docker_services to resolve the published port.
    """
    env_host = os.environ.get("DB_HOST_POSTGIS_VECTOR")
    env_port = os.environ.get("DB_PORT_POSTGIS_VECTOR")
    user = os.environ.get("DB_USER_POSTGIS_VECTOR", "test_user")
    password = os.environ.get("DB_PASSWORD_POSTGIS_VECTOR", "test_password")
    dbname = os.environ.get("DB_NAME_POSTGIS_VECTOR", "test_database")

    if env_host and env_port:
        host, port = env_host, int(env_port)
    else:
        docker_services = request.getfixturevalue("docker_services")
        docker_ip = request.getfixturevalue("docker_ip")
        port = docker_services.port_for("postgis_vector", 5432)
        host = docker_ip

    deadline = time.time() + 90
    while time.time() < deadline and not _pg_ready(host, port, user, password, dbname):
        time.sleep(1.0)
    assert _pg_ready(host, port, user, password, dbname), (
        "PostGIS (pgvector) not ready in time"
    )

    # Prepare databases for the test
    conn = psycopg2.connect(
        host=host, port=port, user=user, password=password, dbname=dbname
    )
    conn.set_session(autocommit=True)
    cur = conn.cursor()
    cur.execute("CREATE DATABASE test_db_vector")
    cur.close()
    conn.close()

    yield {
        "host": host,
        "port": str(port),
        "user": user,
        "password": password,
        "dbname": dbname,
    }

    # Teardown: drop test database
    conn = psycopg2.connect(
        host=host, port=port, user=user, password=password, dbname=dbname
    )
    conn.set_session(autocommit=True)
    cur = conn.cursor()
    # terminate sessions and drop
    cur.execute("""
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = 'test_db_vector' AND pid <> pg_backend_pid();
    """)
    cur.execute("DROP DATABASE IF EXISTS test_db_vector")
    cur.close()
    conn.close()


@pytest.fixture
def postgis_vector_module(postgis_vector_service):
    return PostGISModule(
        postgis_vector_service["host"],
        postgis_vector_service["port"],
        postgis_vector_service["user"],
        postgis_vector_service["password"],
        postgis_vector_service["dbname"],
    )


def test_backup_and_restore_with_pgvector(
    pytestconfig, postgis_vector_service, postgis_vector_module
):
    host = postgis_vector_service["host"]
    port = postgis_vector_service["port"]
    user = postgis_vector_service["user"]
    password = postgis_vector_service["password"]

    backup_file = Path(
        str(pytestconfig.rootdir), "tests", "test_postgis_vector_db_backup.dump"
    )
    pre_sql_file = backup_file.with_suffix(".pre.sql")
    if backup_file.exists():
        os.remove(backup_file)
    if pre_sql_file.exists():
        os.remove(pre_sql_file)

    try:
        # Connect to test DB and create schema + ext
        conn = psycopg2.connect(
            host=host, port=port, user=user, password=password, dbname="test_db_vector"
        )
        cur = conn.cursor()
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        # pgvector package is present in image; this should succeed
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id SERIAL PRIMARY KEY,
                data VARCHAR(255) NOT NULL
            )
        """)
        conn.commit()
        cur.execute("INSERT INTO items (data) VALUES ('Original Data')")
        conn.commit()
        cur.close()
        conn.close()

        # Backup
        assert postgis_vector_module.backup_database("test_db_vector", backup_file)
        assert pre_sql_file.exists(), ".pre.sql not created for vector backup"
        pre_sql = pre_sql_file.read_text()
        assert "CREATE EXTENSION IF NOT EXISTS postgis;" in pre_sql
        assert 'CREATE EXTENSION IF NOT EXISTS "vector";' in pre_sql

        # Mutate data
        conn = psycopg2.connect(
            host=host, port=port, user=user, password=password, dbname="test_db_vector"
        )
        cur = conn.cursor()
        cur.execute("DELETE FROM items")
        cur.execute("INSERT INTO items (data) VALUES ('Altered Data')")
        conn.commit()
        cur.close()
        conn.close()

        # Restore
        assert postgis_vector_module.restore_database("test_db_vector", backup_file)

        # Verify
        conn = psycopg2.connect(
            host=host, port=port, user=user, password=password, dbname="test_db_vector"
        )
        cur = conn.cursor()
        cur.execute("SELECT data FROM items")
        restored = cur.fetchone()[0]
        assert restored == "Original Data"
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'postgis');"
        )
        assert cur.fetchone()[0]
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector');"
        )
        assert cur.fetchone()[0]
        cur.close()
        conn.close()
    finally:
        if backup_file.exists():
            os.remove(backup_file)
        if pre_sql_file.exists():
            os.remove(pre_sql_file)
