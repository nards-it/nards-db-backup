import psycopg2
from psycopg2 import Error
from pathlib import Path
from typing import List
import subprocess
import logging

from app.modules.abstract_module import AbstractModule

# Configura il logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class PostGISModule(AbstractModule):
    """
    Concrete implementation of AbstractModule for PostgreSQL databases with PostGIS,
    providing methods for listing, backing up, and restoring databases.
    """

    def __init__(self, host: str, port: str, username: str, password: str):
        """
        Initializes the PostGISModule with connection details.

        Args:
            host (str): The hostname of the PostgreSQL server.
            port (str): The port number of the PostgreSQL server.
            username (str): The username to connect to the PostgreSQL server.
            password (str): The password to connect to the PostgreSQL server.
        """
        super().__init__(host, port, username, password)

    def _connect(self):
        """
        Establishes a connection to the PostgreSQL server.

        Returns:
            psycopg2.connection: The connection object if successful, None otherwise.
        """
        try:
            connection = psycopg2.connect(
                host=self._host,
                port=self._port,
                user=self._username,
                password=self._password
            )
            logger.info("Successfully connected to PostgreSQL database.")
            return connection
        except Error as e:
            logger.error(f"Error connecting to PostgreSQL database: {e}")
            return None

    def list_all_databases(self) -> List[str]:
        """
        Lists all databases in the PostgreSQL server.

        Returns:
            List[str]: A list of database names.
        """
        connection = self._connect()
        if connection:
            try:
                cursor = connection.cursor()
                cursor.execute("SELECT datname FROM pg_database WHERE datistemplate = false;")
                databases = cursor.fetchall()
                cursor.close()
                return [db[0] for db in databases]
            except Error as e:
                logger.error(f"Error fetching database list: {e}")
                return []
            finally:
                connection.close()
                logger.info("PostgreSQL connection closed after listing databases.")
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
        command = (f"pg_dump -h {self._host} -p {self._port} -U {self._username} -d {name} -F c -b -v -f"
                   f" {destination_file}")
        try:
            # Set the PGPASSWORD environment variable to avoid password prompt
            env = {"PGPASSWORD": self._password}
            result = subprocess.run(command, shell=True, check=True, text=True, env=env)
            logger.info(f"Backup successful for database {name} to {destination_file}.")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Error backing up database {name}: {e}")
            return False

    def restore_database(self, name: str, source_file: Path) -> bool:
        """
        Restores the specified PostGIS database from a backup file.

        Args:
            name (str): The name of the database to restore.
            source_file (Path): The path to the backup file.

        Returns:
            bool: True if the restore was successful, False otherwise.
        """

        # Set environment variable for password
        env = {
            "PGPASSWORD": self._password
        }

        drop_command = (f"psql -h {self._host} -p {self._port} -U {self._username} -d postgres "
                        f"-c 'DROP DATABASE IF EXISTS {name};'")
        create_command = (f"psql -h {self._host} -p {self._port} -U {self._username} -d postgres "
                          f"-c 'CREATE DATABASE {name};'")
        enable_postgis_command = (f"psql -h {self._host} -p {self._port} -U {self._username} -d {name} "
                                  f"-c 'CREATE EXTENSION postgis;'")
        restore_command = f"pg_restore -h {self._host} -p {self._port} -U {self._username} -d {name} {source_file}"

        try:
            # Drop the database
            subprocess.run(drop_command, shell=True, check=True, text=True, encoding='utf-8', env=env)
            logger.info(f"Database {name} dropped successfully.")

            # Create the database
            subprocess.run(create_command, shell=True, check=True, text=True, encoding='utf-8', env=env)
            logger.info(f"Database {name} created successfully.")

            # Enable PostGIS extension
            subprocess.run(enable_postgis_command, shell=True, check=True, text=True, encoding='utf-8', env=env)
            logger.info(f"PostGIS extension enabled for database {name}.")

            # Restore the database from the backup file
            subprocess.run(restore_command, shell=True, check=True, text=True, encoding='utf-8', env=env)
            logger.info(f"Restore successful for database {name} from {source_file}.")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(
                f"Error restoring database {name}: {e}. "
                f"Command: {drop_command if e.cmd == drop_command else (enable_postgis_command if e.cmd == enable_postgis_command else restore_command)}")
            return False
        except FileNotFoundError:
            logger.error(f"Backup file {source_file} not found.")
            return False
        except Exception as e:
            logger.error(f"Unexpected error occurred while restoring database {name}: {e}")
            return False
