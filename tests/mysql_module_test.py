import os
import sys
# insert root directory into python module search path
sys.path.insert(1, os.getcwd())

import pytest
from pathlib import Path
import mysql.connector
from app.modules.mysql_module import MySQLModule


@pytest.fixture(scope='module')
def mysql_connection():
    # Setup: connessione al database
    connection = mysql.connector.connect(
        host='mysql',
        port='3306',
        user='test_user',
        password='test_password'
    )
    cursor = connection.cursor()

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
    cursor.close()
    connection.close()


@pytest.fixture
def mysql_module():
    return MySQLModule('mysql', '3306', 'test_user', 'test_password')


def test_list_all_databases(mysql_module):
    result = mysql_module.list_all_databases()
    assert 'test_db' in result


def test_backup_and_restore_database(mysql_connection, mysql_module):
    connection, cursor = mysql_connection

    # Inserimento di dati nel database
    cursor.execute("INSERT INTO test_table (data) VALUES ('Original Data')")
    connection.commit()

    # Percorso del file di backup
    backup_file = Path('/backups/test_db_backup.sql')

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
