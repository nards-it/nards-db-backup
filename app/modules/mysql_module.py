import time

import mysql.connector
from mysql.connector import Error
from pathlib import Path
from typing import List
import subprocess
import logging

from app.modules.abstract_module import AbstractModule

# Configura il logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class MySQLModule(AbstractModule):
    """
    Concrete implementation of AbstractModule for MySQL databases, providing methods
    for listing, backing up, and restoring databases.
    """

    def __init__(self, host: str, port: str, username: str, password: str):
        """
        Initializes the MySQLModule with connection details.

        Args:
            host (str): The hostname of the MySQL server.
            port (str): The port number of the MySQL server.
            username (str): The username to connect to the MySQL server.
            password (str): The password to connect to the MySQL server.
        """
        super().__init__(host, port, username, password)

    def _connect(self):
        """
        Establishes a connection to the MySQL server.

        Returns:
            mysql.connector.connection.MySQLConnection: The connection object if successful, None otherwise.
        """
        for attempt in range(1, 7):
            try:
                logger.info(f"Connection attempt {attempt} to MySQL database")
                connection = mysql.connector.connect(
                    host=self._host,
                    port=self._port,
                    user=self._username,
                    password=self._password
                )
                logger.info("Successfully connected to MySQL database.")
                return connection
            except Error as e:
                logger.error(f"Error connecting to MySQL database: {e}")
                logger.info(f"Waiting {5*attempt} seconds to connect again to MySQL database")
                time.sleep(5*attempt)

        logger.error("Error connecting to MySQL database, no more attempts.")

    def list_all_databases(self) -> List[str]:
        """
        Lists all databases in the MySQL server.

        Returns:
            List[str]: A list of database names.
        """
        connection = self._connect()
        if connection:
            try:
                cursor = connection.cursor()
                cursor.execute("SHOW DATABASES")
                databases = cursor.fetchall()
                cursor.close()
                system_databases = ['information_schema', 'mysql', 'performance_schema', 'sys']
                return [db[0] for db in databases if db[0] not in system_databases]
            except Error as e:
                logger.error(f"Error fetching database list: {e}")
                return []
            finally:
                connection.close()
                logger.info("MySQL connection closed after listing databases.")
        else:
            logger.error("Unknown error connecting to database.")
            return []

    def backup_database(self, name: str, destination_file: Path) -> bool:
        """
        Backs up the specified database to a file.

        Args:
            name (str): The name of the database to back up.
            destination_file (Path): The path to the file where the backup will be stored.

        Returns:
            bool: True if the backup was successful, False otherwise.
        """
        command = (f"mysqldump -h {self._host} -P {self._port} -u {self._username} -p{self._password} {name} >"
                   f" {destination_file}")
        try:
            subprocess.run(command, shell=True, check=True, text=True)
            logger.info(f"Backup successful for database {name} to {destination_file}.")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Error backing up database {name}: {e}")
            return False

    def restore_database(self, name: str, source_file: Path) -> bool:
        """
        Restores the specified database from a backup file.

        Args:
            name (str): The name of the database to restore.
            source_file (Path): The path to the backup file.

        Returns:
            bool: True if the restore was successful, False otherwise.
        """
        drop_command = (f"mysql -h {self._host} -P {self._port} -u {self._username} -p{self._password}"
                        f" -e 'DROP DATABASE IF EXISTS {name}; CREATE DATABASE {name};'")
        restore_command = (f"mysql -h {self._host} -P {self._port} -u {self._username} -p{self._password} {name}"
                           f" < {source_file}")

        try:
            # Drop and recreate the database
            subprocess.run(drop_command, shell=True, check=True, text=True, encoding='utf-8')
            logger.info(f"Database {name} dropped and recreated successfully.")

            # Restore the database from the backup file
            subprocess.run(restore_command, shell=True, check=True, text=True, encoding='utf-8')
            logger.info(f"Restore successful for database {name} from {source_file}.")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(
                f"Error restoring database {name}: {e}. Command: "
                f"{drop_command if e.cmd == drop_command else restore_command}")
            return False
        except FileNotFoundError:
            logger.error(f"Backup file {source_file} not found.")
            return False
        except Exception as e:
            logger.error(f"Unexpected error occurred while restoring database {name}: {e}")
            return False
