import psycopg2
from psycopg2 import Error
from pathlib import Path
from typing import List
import subprocess
import logging
import json
import os

from app.modules.abstract_module import AbstractModule

# Configura il logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class PostGISModule(AbstractModule):
    """
    Concrete implementation of AbstractModule for PostgreSQL databases with PostGIS,
    providing methods for listing, backing up, and restoring databases.
    """

    def __init__(
        self, host: str, port: str, username: str, password: str, maintenance_db: str
    ):
        """
        Initializes the PostGISModule with connection details.

        Args:
            host (str): The hostname of the PostgreSQL server.
            port (str): The port number of the PostgreSQL server.
            username (str): The username to connect to the PostgreSQL server.
            password (str): The password to connect to the PostgreSQL server.
        """
        super().__init__(host, port, username, password, maintenance_db)

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
                password=self._password,
                dbname=self._maintenance_db,
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
                cursor.execute(
                    "SELECT datname FROM pg_database WHERE datistemplate = false;"
                )
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
        # Capture used extensions
        extensions = []
        conn_ext = None
        cur = None
        try:
            # Connect to the target database 'name' to fetch its extensions
            conn_ext = psycopg2.connect(
                host=self._host,
                port=self._port,
                user=self._username,
                password=self._password,
                dbname=name
            )
            cur = conn_ext.cursor()
            cur.execute("SELECT extname FROM pg_extension WHERE extname <> 'plpgsql';")
            extensions = [r[0] for r in cur.fetchall()]
            logger.info(f"Successfully retrieved extensions for database '{name}': {extensions}")
        except Error as e: # Catch psycopg2 specific errors for connection or query
            logger.warning(f"Database error while retrieving extensions for '{name}': {e}. Proceeding with empty extensions list.")
        except Exception as e: # Catch other unexpected errors
            logger.warning(f"Unexpected error while retrieving extensions for '{name}': {e}. Proceeding with empty extensions list.")
        finally:
            if cur:
                cur.close()
            if conn_ext:
                conn_ext.close()

        # Generate .pre.sql file with extension creation commands
        pre_sql_file = destination_file.with_suffix('.pre.sql')
        pre_sql_content = []
        # Always add postgis extension first for a PostGISModule
        pre_sql_content.append("CREATE EXTENSION IF NOT EXISTS postgis;\n")

        # Add other detected extensions, ensuring postgis is not duplicated if detected
        for ext_name in extensions:
            if ext_name.lower() != 'postgis':
                pre_sql_content.append(f'CREATE EXTENSION IF NOT EXISTS "{ext_name}";\n')
        
        try:
            pre_sql_file.write_text("".join(pre_sql_content))
            logger.info(f"Saved pre-restore SQL script for extensions to {pre_sql_file}")
            if not extensions: # Log if only postgis was added (no other extensions detected)
                 logger.info(f"No additional extensions (beyond PostGIS) were detected for database '{name}' to include in {pre_sql_file}.")
        except Exception as e:
            logger.warning(f"Failed writing pre-restore SQL script {pre_sql_file} for database '{name}': {e}")
        
        command = (f"pg_dump --inserts --column-inserts -h {self._host} -p {self._port} -U {self._username} -d {name} -F c -b -v -f"
                   f" {destination_file}")
        try:
            # Set the PGPASSWORD environment variable to avoid password prompt
            env = {"PGPASSWORD": self._password}
            subprocess.run(command, shell=True, check=True, text=True, env=env)
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
        env = {"PGPASSWORD": self._password}

        drop_command = (
            f"psql -h {self._host} -p {self._port} -U {self._username} -d postgres "
            f"-c 'DROP DATABASE IF EXISTS {name};'"
        )
        create_command = (
            f"psql -h {self._host} -p {self._port} -U {self._username} -d postgres "
            f"-c 'CREATE DATABASE {name};'"
        )
        enable_postgis_command = (
            f"psql -h {self._host} -p {self._port} -U {self._username} -d {name} "
            f"-c 'CREATE EXTENSION postgis;'"
        )
        clean_param = ""
        if os.environ.get("PG_RESTORE_CLEAN") == "true":
            clean_param = "--clean --if-exists"
        restore_command = f"pg_restore {clean_param} -h {self._host} -p {self._port} -U {self._username} -d {name} {source_file}"

        try:
            # Drop the database
            subprocess.run(
                drop_command,
                shell=True,
                check=True,
                text=True,
                encoding="utf-8",
                env=env,
            )
            logger.info(f"Database {name} dropped successfully.")

            # Create the database
            subprocess.run(
                create_command,
                shell=True,
                check=True,
                text=True,
                encoding="utf-8",
                env=env,
            )
            logger.info(f"Database {name} created successfully.")

            # Execute .pre.sql script if it exists to create extensions
            pre_sql_file = source_file.with_suffix('.pre.sql')
            if pre_sql_file.exists():
                logger.info(f"Found pre-restore SQL script: {pre_sql_file}. Attempting to execute it.")
                try:
                    execute_pre_sql_command = (
                        f"psql -h {self._host} -p {self._port} -U {self._username} "
                        f"-d \"{name}\" -f \"{pre_sql_file}\""
                    )
                    # Capture output for better logging, especially errors
                    result = subprocess.run(
                        execute_pre_sql_command, shell=True, check=True, text=True, 
                        env=env, capture_output=True, encoding='utf-8'
                    )
                    logger.info(f"Successfully executed pre-restore SQL script {pre_sql_file}.")
                    if result.stdout:
                        logger.debug(f"Output from {pre_sql_file} execution (stdout):\n{result.stdout}")
                    if result.stderr: # Log stderr even on success, as psql might output notices here
                        logger.info(f"Output from {pre_sql_file} execution (stderr):\n{result.stderr}")
                except subprocess.CalledProcessError as e:
                    logger.error(
                        f"Error executing pre-restore SQL script {pre_sql_file} for database '{name}'. "
                        f"Command: '{e.cmd}'. Return code: {e.returncode}."
                    )
                    if e.stdout:
                        logger.error(f"Stdout from failed pre-sql script:\n{e.stdout}")
                    if e.stderr:
                        logger.error(f"Stderr from failed pre-sql script:\n{e.stderr}")
                    # Critical: If extensions (like PostGIS) cannot be created,
                    # the subsequent pg_restore is likely to fail or result in a corrupted database.
                    # Therefore, we stop the restore process immediately.
                    return False
                except Exception as e:
                    logger.error(f"Unexpected error executing pre-restore SQL script {pre_sql_file}: {e}")
                    # Critical: If extensions (like PostGIS) cannot be created due to an unexpected error,
                    # the subsequent pg_restore is likely to fail or result in a corrupted database.
                    # Therefore, we stop the restore process immediately.
                    return False
            else:
                logger.warning(f"Pre-restore SQL script {pre_sql_file} not found. "
                               f"Extensions (beyond those in the main dump) might not be restored.")

            # Restore the database from the backup file
            subprocess.run(
                restore_command,
                shell=True,
                check=True,
                text=True,
                encoding="utf-8",
                env=env,
            )
            logger.info(f"Restore successful for database {name} from {source_file}.")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(
                f"Error restoring database {name}: {e}. "
                f"Command: {drop_command if e.cmd == drop_command else (enable_postgis_command if e.cmd == enable_postgis_command else restore_command)}"
            )
            return False
        except FileNotFoundError:
            logger.error(f"Backup file {source_file} not found.")
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error occurred while restoring database {name}: {e}"
            )
            return False
