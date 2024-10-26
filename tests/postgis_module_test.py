import os
import sys

from psycopg2 import Error
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from app.modules.postgis_module import PostGISModule

# insert root directory into python module search path
sys.path.insert(1, os.getcwd())

import pytest
from pathlib import Path
import psycopg2

@pytest.fixture(scope="session")
def docker_compose_file(pytestconfig):
    return os.path.join(str(pytestconfig.rootdir), "tests", "docker-compose.yml")


def check_postgis_connection(host, port, user, password, database=None):
    """Check if Postgis server is ready for connections."""
    connection = None
    try:
        # Establish a connection to the Postgis server
        connection = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database
        )

        if connection:
            print("Postgis server is ready for connections.")
            return True

    except Error:
        return False

    finally:
        # Close the connection if it was established
        if connection is not None:
            connection.close()

@pytest.fixture(scope='session', autouse=True)
def postgis_connection(docker_ip, docker_services):
    docker_port = docker_services.port_for("postgis", 5432)

    # Wait until docker iservice is ready to accept connections
    docker_services.wait_until_responsive(
        timeout=60.0, pause=0.1, check= lambda: check_postgis_connection(
            host=docker_ip,
            port=docker_port,
            user='test_user',
            password='test_password',
            database='test_database'
        )
    )

    # Setup: connessione al database
    connection = psycopg2.connect(
        host=docker_ip,
        port=docker_port,
        user='test_user',
        password='test_password',
        database='test_database'
    )

    # Create databases without a transaction
    connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = connection.cursor()

    # Creazione di un database di test da elencare
    cursor.execute("CREATE DATABASE test_db_2")

    # Creazione di un database di test
    cursor.execute("CREATE DATABASE test_db")

    cursor.close()
    connection.close()

    yield

    cursor.close()
    connection.close()

    # Setup: connessione al database
    connection = psycopg2.connect(
        host=docker_ip,
        port=docker_port,
        user='test_user',
        password='test_password',
        database='test_database'
    )

    # Create databases without a transaction
    connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = connection.cursor()

    # Teardown: eliminazione del database di test
    cursor.execute("DROP DATABASE test_db")
    cursor.execute("DROP DATABASE test_db_2")

    cursor.close()
    connection.close()


@pytest.fixture
def postgis_module(docker_ip, docker_services):
    docker_port = docker_services.port_for("postgis", 5432)
    return PostGISModule(docker_ip, docker_port, 'test_user', 'test_password', "test_database")


def test_list_all_databases(postgis_module, docker_services):
    result = postgis_module.list_all_databases()
    assert 'test_db_2' in result
    assert 'test_db' in result


def test_backup_and_restore_database(pytestconfig, docker_ip, docker_services, postgis_module):
    docker_port = docker_services.port_for("postgis", 5432)

    # Percorso del file di backup
    backup_file = Path(str(pytestconfig.rootdir), "tests", "test_postgis_db_backup.sql")
    if backup_file.exists():
        os.remove(backup_file)
    try:

        # Setup: connessione al database
        connection = psycopg2.connect(
            host=docker_ip,
            port=docker_port,
            user='test_user',
            password='test_password',
            database='test_db'
        )
        cursor = connection.cursor()

        cursor.execute("""
                    CREATE TABLE IF NOT EXISTS test_table (
                        id SERIAL PRIMARY KEY,
                        data VARCHAR(255) NOT NULL
                    )
                """)
        connection.commit()

        # Inserimento di dati nel database
        cursor.execute("INSERT INTO test_table (data) VALUES ('Original Data')")
        connection.commit()

        # Esecuzione del backup
        backup_result = postgis_module.backup_database('test_db', backup_file)
        assert backup_result

        # Alterazione dei dati
        cursor.execute("DELETE FROM test_table")
        cursor.execute("INSERT INTO test_table (data) VALUES ('Altered Data')")
        connection.commit()

        cursor.close()
        connection.close()

        # Esecuzione del restore
        restore_result = postgis_module.restore_database('test_db', backup_file)
        assert restore_result

        # Setup: connessione al database
        connection = psycopg2.connect(
            host=docker_ip,
            port=docker_port,
            user='test_user',
            password='test_password',
            database='test_db'
        )
        cursor = connection.cursor()

        cursor.execute("""
                    CREATE TABLE IF NOT EXISTS test_table (
                        id SERIAL PRIMARY KEY,
                        data VARCHAR(255) NOT NULL
                    )
                """)
        connection.commit()

        # Verifica che i dati originali siano stati ripristinati
        cursor.execute("SELECT data FROM test_table")
        restored_data = cursor.fetchone()[0]

        cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_extension
                        WHERE extname = 'postgis'
                    );
                """)
        has_postgis = cursor.fetchone()[0]
        assert has_postgis, "PostGIS extension is not present in the database after restore."

        cursor.close()
        connection.close()

        assert restored_data == 'Original Data'

    finally:
        if backup_file.exists():
            os.remove(backup_file)
