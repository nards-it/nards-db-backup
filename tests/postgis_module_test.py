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
import json


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

    # Wait until docker service is ready to accept connections
    docker_services.wait_until_responsive(
        timeout=60.0, pause=0.1, check= lambda: check_postgis_connection(
            host=docker_ip,
            port=docker_port,
            user='test_user',
            password='test_password',
            database='test_database'
        )
    )

    # Setup: connect to the database
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

    # Create a test database to be listed
    cursor.execute("CREATE DATABASE test_db_2")

    # Create a test database
    cursor.execute("CREATE DATABASE test_db")

    cursor.close()
    connection.close()

    yield

    cursor.close()
    connection.close()

    # Setup: connect to the database
    connection = psycopg2.connect(
        host=host, port=port, user=user, password=password, dbname=db_name
    )
    connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = connection.cursor()

    # Teardown: delete the test database
    # Terminate other connections to test_db before dropping
    cursor.execute(f"""
    SELECT pg_terminate_backend(pid)
    FROM pg_stat_activity
    WHERE datname = 'test_db' AND pid <> pg_backend_pid();
    """)
    connection.commit() # Commit termination
    cursor.execute("DROP DATABASE test_db")
    # For test_db_2, termination might also be needed if tests connect to it and leave sessions
    cursor.execute(f"""
    SELECT pg_terminate_backend(pid)
    FROM pg_stat_activity
    WHERE datname = 'test_db_2' AND pid <> pg_backend_pid();
    """)
    connection.commit() # Commit termination
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


def test_backup_and_restore_database(pytestconfig, docker_ip, docker_services, postgis_module):
    docker_port = docker_services.port_for("postgis", 5432)

    # Backup file path
    backup_file = Path(str(pytestconfig.rootdir), "tests", "test_postgis_db_backup.sql")
    pre_sql_file = backup_file.with_suffix('.pre.sql') # Define pre_sql_file path

    if backup_file.exists():
        os.remove(backup_file)
    if pre_sql_file.exists(): # Ensure .pre.sql is also cleaned up
        os.remove(pre_sql_file)
    try:

        # Setup: connect to the database
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

        # Insert data into the database
        cursor.execute("INSERT INTO test_table (data) VALUES ('Original Data')")
        connection.commit()

        # Enable pgvector before dump
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        connection.commit()

        # Perform backup
        backup_result = postgis_module.backup_database('test_db', backup_file)
        assert backup_result

        # Verifica che il file .pre.sql delle estensioni sia stato creato e il suo contenuto
        assert pre_sql_file.exists(), f".pre.sql file not created: {pre_sql_file}"
        pre_sql_content = pre_sql_file.read_text()
        assert "CREATE EXTENSION IF NOT EXISTS postgis;" in pre_sql_content, "Command for postgis missing in .pre.sql"
        assert 'CREATE EXTENSION IF NOT EXISTS "vector";' in pre_sql_content, "Command for vector missing in .pre.sql"

        # Alter data
        cursor.execute("DELETE FROM test_table")
        cursor.execute("INSERT INTO test_table (data) VALUES ('Altered Data')")
        connection.commit()

        cursor.close()
        connection.close()

        # Perform restore
        restore_result = postgis_module.restore_database('test_db', backup_file)
        assert restore_result

        # Setup: connect to the database
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

        # Verify that original data has been restored
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

        # Verify that pgvector has been restored
        cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector');")
        has_vector = cursor.fetchone()[0]
        assert has_vector, "pgvector extension is not present in the database after restore."

        cursor.close()
        connection.close()

    finally:
        if backup_file.exists():
            os.remove(backup_file)
        # if pre_sql_file.exists(): # Temporarily commented out to inspect the .pre.sql file
        #     os.remove(pre_sql_file)
