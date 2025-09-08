import os
import sys
import time
from mysql.connector import Error

# insert root directory into python module search path
sys.path.insert(1, os.getcwd())

import pytest
from pathlib import Path
import mysql.connector
from app.modules.mysql_module import MySQLModule


@pytest.fixture(scope="session", autouse=True)
def mysql_connection():
    """
    Waits for the MySQL container to be ready, then sets up the database for tests.
    """
    host = os.environ.get("DB_HOST_MYSQL")
    port = os.environ.get("DB_PORT_MYSQL")
    user = "root"
    password = "rootpassword"

    connection = None
    retries = 20
    while retries > 0:
        try:
            connection = mysql.connector.connect(
                host=host,
                port=port,
                user=user,
                password=password,
            )
            if connection.is_connected():
                print("MySQL server is ready for connections.")
                break
        except Error as e:
            print(f"Waiting for MySQL... ({retries} retries left)")
            retries -= 1
            time.sleep(3)
            if retries == 0:
                raise e

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
def mysql_module():
    """
    Initializes the MySQLModule with connection details from environment variables.
    """
    host = os.environ.get("DB_HOST_MYSQL")
    port = os.environ.get("DB_PORT_MYSQL")
    user = "root"
    password = "rootpassword"
    db_name = os.environ.get("DB_NAME_MYSQL")
    return MySQLModule(host, port, user, password, db_name)


def test_list_all_databases(mysql_module):
    """
    Tests that the list_all_databases method returns the created test databases.
    """
    result = mysql_module.list_all_databases()
    assert "test_db_2" in result
    assert "test_db" in result


def test_backup_and_restore_database(pytestconfig, mysql_connection, mysql_module):
    """
    Tests the full backup and restore cycle for a MySQL database.
    """
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
        backup_result = mysql_module.backup_database("test_db", str(backup_file))
        assert backup_result

        # Alterazione dei dati
        cursor.execute("DELETE FROM test_table")
        cursor.execute("INSERT INTO test_table (data) VALUES ('Altered Data')")
        connection.commit()

        # Esecuzione del restore
        restore_result = mysql_module.restore_database("test_db", str(backup_file))
        assert restore_result

        # Verifica che i dati originali siano stati ripristinati
        cursor.execute("USE test_db")
        cursor.execute("SELECT data FROM test_table")
        restored_data = cursor.fetchone()[0]
        assert restored_data == "Original Data"

    finally:
        if backup_file.exists():
            os.remove(backup_file)
