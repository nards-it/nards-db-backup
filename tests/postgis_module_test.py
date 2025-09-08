import os
import sys
import time
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from app.modules.postgis_module import PostGISModule

# insert root directory into python module search path
sys.path.insert(1, os.getcwd())

import pytest
from pathlib import Path
import psycopg2


@pytest.fixture(scope="session", autouse=True)
def postgis_connection():
    """
    Waits for the PostGIS container to be ready, then sets up the database for tests.
    """
    host = os.environ.get("DB_HOST_POSTGIS")
    port = os.environ.get("DB_PORT_POSTGIS")
    user = os.environ.get("DB_USER_POSTGIS")
    password = os.environ.get("DB_PASSWORD_POSTGIS")
    db_name = os.environ.get("DB_NAME_POSTGIS")

    connection = None
    retries = 20
    while retries > 0:
        try:
            connection = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                dbname=db_name,
            )
            if connection:
                print("PostGIS server is ready for connections.")
                break
        except Exception as e:
            print(f"Waiting for PostGIS... ({retries} retries left)")
            retries -= 1
            time.sleep(3)
            if retries == 0:
                raise e

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

    # Teardown: eliminazione del database di test
    connection = psycopg2.connect(
        host=host, port=port, user=user, password=password, dbname=db_name
    )
    connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = connection.cursor()
    cursor.execute("DROP DATABASE test_db")
    cursor.execute("DROP DATABASE test_db_2")

    cursor.close()
    connection.close()


@pytest.fixture
def postgis_module():
    """
    Initializes the PostGISModule with connection details from environment variables.
    """
    host = os.environ.get("DB_HOST_POSTGIS")
    port = os.environ.get("DB_PORT_POSTGIS")
    user = os.environ.get("DB_USER_POSTGIS")
    password = os.environ.get("DB_PASSWORD_POSTGIS")
    db_name = os.environ.get("DB_NAME_POSTGIS")
    return PostGISModule(host, port, user, password, db_name)


def test_list_all_databases(postgis_module):
    """
    Tests that the list_all_databases method returns the created test databases.
    """
    result = postgis_module.list_all_databases()
    assert "test_db_2" in result
    assert "test_db" in result


def test_backup_and_restore_database(pytestconfig, postgis_module):
    """
    Tests the full backup and restore cycle for a PostGIS database.
    """
    host = os.environ.get("DB_HOST_POSTGIS")
    port = os.environ.get("DB_PORT_POSTGIS")
    user = os.environ.get("DB_USER_POSTGIS")
    password = os.environ.get("DB_PASSWORD_POSTGIS")

    # Percorso del file di backup
    backup_file = Path(str(pytestconfig.rootdir), "tests", "test_postgis_db_backup.sql")
    if backup_file.exists():
        os.remove(backup_file)
    try:
        # Setup: connessione al database
        connection = psycopg2.connect(
            host=host, port=port, user=user, password=password, database="test_db"
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
        backup_result = postgis_module.backup_database("test_db", str(backup_file))
        assert backup_result

        # Alterazione dei dati
        cursor.execute("DELETE FROM test_table")
        cursor.execute("INSERT INTO test_table (data) VALUES ('Altered Data')")
        connection.commit()

        cursor.close()
        connection.close()

        # Esecuzione del restore
        restore_result = postgis_module.restore_database("test_db", str(backup_file))
        assert restore_result

        # Setup: connessione al database
        connection = psycopg2.connect(
            host=host, port=port, user=user, password=password, database="test_db"
        )
        cursor = connection.cursor()

        # Verifica che i dati originali siano stati ripristinati
        cursor.execute("SELECT data FROM test_table")
        restored_data = cursor.fetchone()[0]
        assert restored_data == "Original Data"

        cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_extension
                        WHERE extname = 'postgis'
                    );
                """)
        has_postgis = cursor.fetchone()[0]
        assert has_postgis, (
            "PostGIS extension is not present in the database after restore."
        )

        cursor.close()
        connection.close()

    finally:
        if backup_file.exists():
            os.remove(backup_file)
