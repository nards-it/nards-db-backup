import os
import sys

from mysql.connector import Error

# insert root directory into python module search path
sys.path.insert(1, os.getcwd())

import pytest
from pathlib import Path
import mysql.connector
from app.modules.mysql_module import MySQLModule

@pytest.fixture(scope="session")
def docker_compose_file(pytestconfig):
    return os.path.join(str(pytestconfig.rootdir), "tests", "docker-compose.yml")


def check_mysql_connection(host, port, user, password, database=None):
    """Check if MySQL server is ready for connections."""
    connection = None
    try:
        # Establish a connection to the MySQL server
        connection = mysql.connector.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database
        )

        if connection.is_connected():
            print("MySQL server is ready for connections.")
            return True

    except Error:
        return False

    finally:
        # Close the connection if it was established
        if connection is not None and connection.is_connected():
            connection.close()

@pytest.fixture(scope='session', autouse=True)
def mysql_connection(docker_ip, docker_services):
    docker_port = docker_services.port_for("mysql", 3306)

    # Wait until docker iservice is ready to accept connections
    docker_services.wait_until_responsive(
        timeout=60.0, pause=0.1, check= lambda: check_mysql_connection(
            host=docker_ip,
            port=docker_port,
            user='test_user',
            password='test_password'
        )
    )

    # Setup: connessione al database
    connection = mysql.connector.connect(
        host=docker_ip,
        port=docker_port,
        user='root',
        password='rootpassword'
    )
    cursor = connection.cursor()

    # Creazione di un database di test da elencare
    cursor.execute("CREATE DATABASE IF NOT EXISTS test_db_2")

    # Creazione di un database di test
    cursor.execute("CREATE DATABASE IF NOT EXISTS test_db")
    cursor.execute("USE test_db")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS test_table (
            id INT AUTO_INCREMENT PRIMARY KEY,
            data VARCHAR(255) NOT NULL
        )
    """)
    connection.commit()

    yield connection, cursor

    # Teardown: eliminazione del database di test
    cursor.execute("DROP DATABASE test_db")
    cursor.execute("DROP DATABASE test_db_2")
    cursor.close()
    connection.close()


@pytest.fixture
def mysql_module(docker_ip, docker_services):
    docker_port = docker_services.port_for("mysql", 3306)
    return MySQLModule(docker_ip, docker_port, 'root', 'rootpassword', "test_database")


def test_list_all_databases(mysql_module, docker_services):
    result = mysql_module.list_all_databases()
    assert 'test_db_2' in result
    assert 'test_db' in result


def test_backup_and_restore_database(pytestconfig, mysql_connection, mysql_module):
    connection, cursor = mysql_connection

    # Percorso del file di backup
    backup_file = Path(str(pytestconfig.rootdir), "tests", "test_mysql_db_backup.sql")
    if backup_file.exists():
        os.remove(backup_file)
    try:

        # Inserimento di dati nel database
        cursor.execute("INSERT INTO test_table (data) VALUES ('Original Data')")
        connection.commit()

        # Esecuzione del backup
        backup_result = mysql_module.backup_database('test_db', backup_file)
        assert backup_result

        # Alterazione dei dati
        cursor.execute("DELETE FROM test_table")
        cursor.execute("INSERT INTO test_table (data) VALUES ('Altered Data')")
        connection.commit()

        # Esecuzione del restore
        restore_result = mysql_module.restore_database('test_db', backup_file)
        assert restore_result

        # Verifica che i dati originali siano stati ripristinati
        cursor.execute("SELECT data FROM test_table")
        restored_data = cursor.fetchone()[0]
        assert restored_data == 'Original Data'

    finally:
        if backup_file.exists():
            os.remove(backup_file)
