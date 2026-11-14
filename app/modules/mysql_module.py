import logging
import os
import subprocess
import time
from pathlib import Path

import mysql.connector
from mysql.connector import Error

from app.modules.abstract_module import AbstractModule

# Configura il logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class MySQLModule(AbstractModule):
    """
    Concrete implementation of AbstractModule for MySQL databases, providing methods
    for listing, backing up, and restoring databases.
    """

    def __init__(
        self,
        host: str,
        port: str,
        username: str,
        password: str,
        maintenance_db: str,
        file_extension: str = ".backup",
    ):
        """
        Initializes the MySQLModule with connection details.

        Args:
            host (str): The hostname of the MySQL server.
            port (str): The port number of the MySQL server.
            username (str): The username to connect to the MySQL server.
            password (str): The password to connect to the MySQL server.
        """
        super().__init__(host, port, username, password, maintenance_db, file_extension)

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
                    password=self._password,
                    database=self._maintenance_db,
                )
                logger.info("Successfully connected to MySQL database.")
                return connection
            except Error as e:
                logger.error(f"Error connecting to MySQL database: {e}")
                logger.info(
                    f"Waiting {5 * attempt} seconds to connect again to MySQL database"
                )
                time.sleep(5 * attempt)

        logger.error("Error connecting to MySQL database, no more attempts.")

    def list_all_databases(self) -> list[str]:
        """
        Lists all databases in the MySQL server.

        Returns:
            list[str]: A list of database names.
        """
        connection = self._connect()
        if connection:
            try:
                cursor = connection.cursor()
                cursor.execute("SHOW DATABASES")
                databases = cursor.fetchall()
                cursor.close()
                system_databases = [
                    "information_schema",
                    "mysql",
                    "performance_schema",
                    "sys",
                ]
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

    def _backup_database(self, name: str, destination_file: Path) -> bool:
        """
        Backs up the specified database to a file.

        Args:
            name (str): The name of the database to back up.
            destination_file (Path): The path to the file where the backup will be stored.

        Returns:
            bool: True if the backup was successful, False otherwise.
        """
        ssl_mode_param = ""
        if os.environ.get("MYSQL_SSL_MODE") == "DISABLED":
            ssl_mode_param = "--skip-ssl"

        command = (
            f"mysqldump {ssl_mode_param} --complete-insert -h {self._host} -P {self._port} -u {self._username} -p{self._password} {name} >"
            f" {destination_file}"
        )
        try:
            result = subprocess.run(
                command, shell=True, check=True, text=True, stderr=subprocess.PIPE
            )
            self._log_stderr(result.stderr)
            logger.info(f"Backup successful for database {name} to {destination_file}.")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(
                "Error backing up database %s: command exited with status %s; stderr: %s",
                name,
                e.returncode,
                self._redact_password(e.stderr or "(no diagnostic output)"),
            )
            return False

    def _restore_database(self, name: str, source_file: Path) -> bool:
        """
        Restores the specified database from a backup file.

        Args:
            name (str): The name of the database to restore.
            source_file (Path): The path to the backup file.

        Returns:
            bool: True if the restore was successful, False otherwise.
        """
        ssl_mode_param = ""
        if os.environ.get("MYSQL_SSL_MODE") == "DISABLED":
            ssl_mode_param = "--skip-ssl"

        drop_command = (
            f"mysql {ssl_mode_param} -h {self._host} -P {self._port} -u {self._username} -p{self._password}"
            f" -e 'DROP DATABASE IF EXISTS {name}; CREATE DATABASE {name};'"
        )
        restore_command = (
            f"mysql {ssl_mode_param} -h {self._host} -P {self._port} -u {self._username} -p{self._password} {name}"
            f" < {source_file}"
        )

        try:
            # Drop and recreate the database
            result = subprocess.run(
                drop_command,
                shell=True,
                check=True,
                text=True,
                encoding="utf-8",
                stderr=subprocess.PIPE,
            )
            self._log_stderr(result.stderr)
            logger.info(f"Database {name} dropped and recreated successfully.")

            # Restore the database from the backup file
            result = subprocess.run(
                restore_command,
                shell=True,
                check=True,
                text=True,
                encoding="utf-8",
                stderr=subprocess.PIPE,
            )
            self._log_stderr(result.stderr)
            logger.info(f"Restore successful for database {name} from {source_file}.")
            return True
        except subprocess.CalledProcessError as e:
            operation = "database recreation" if e.cmd == drop_command else "import"
            logger.error(
                "Error restoring database %s during %s: command exited with status %s; stderr: %s",
                name,
                operation,
                e.returncode,
                self._redact_password(e.stderr or "(no diagnostic output)"),
            )
            return False
        except FileNotFoundError:
            logger.error(f"Backup file {source_file} not found.")
            return False
        except Exception as e:  # Catch other unexpected errors  # noqa: BLE001
            logger.error(
                "Unexpected error restoring database %s (%s): %s",
                name,
                type(e).__name__,
                self._redact_password(str(e)),
            )
            return False

    def _redact_password(self, message: str) -> str:
        """Mask the configured password in diagnostic text before logging.

        Both the literal password and its escaped Python representation are
        removed, because exception messages can contain either form.
        """
        if not self._password:
            return message
        escaped = repr(self._password)[1:-1]
        for value in sorted({self._password, escaped}, key=len, reverse=True):
            message = message.replace(value, "[REDACTED]")
        return message

    def _log_stderr(self, stderr: str | None) -> None:
        """Log command warnings without exposing the configured password."""
        if stderr:
            logger.warning("MySQL command stderr: %s", self._redact_password(stderr))
