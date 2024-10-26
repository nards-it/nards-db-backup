from abc import ABCMeta, abstractmethod
from pathlib import Path
from typing import List


class AbstractModule(metaclass=ABCMeta):
    """
    Abstract base class for a database module, providing methods for listing,
    backing up, and restoring databases.
    """

    def __init__(self, host: str, port: str, username: str, password: str, maintenance_db: str):
        """
        Initializes the database module with connection details.

        Args:
            host (str): The hostname of the database server.
            port (str): The port number of the database server.
            username (str): The username to connect to the database.
            password (str): The password to connect to the database.
            maintenance_db (str): The name of the database used for maintenance.
        """
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._maintenance_db = maintenance_db

    @property
    def host(self) -> str:
        """
        Returns the hostname of the database server.

        Returns:
            str: The hostname of the database server.
        """
        return self._host

    @property
    def port(self) -> str:
        """
        Returns the port number of the database server.

        Returns:
            str: The port number of the database server.
        """
        return self._port

    @property
    def username(self) -> str:
        """
        Returns the username to connect to the database.

        Returns:
            str: The username to connect to the database.
        """
        return self._username

    @property
    def password(self) -> str:
        """
        Returns the password to connect to the database.

        Returns:
            str: The password to connect to the database.
        """
        return self._password

    @property
    def maintenance_db(self) -> str:
        """
        Returns the name of the database used for maintenance.

        Returns:
            str: The name of the database used for maintenance.
        """
        return self._password

    @abstractmethod
    def list_all_databases(self) -> List[str]:
        """
        Lists all databases in the database server.

        Returns:
            List[str]: A list of database names.
        """
        raise Exception("Unsupported method")

    @abstractmethod
    def backup_database(self, name: str, destination_file: Path) -> bool:
        """
        Backs up the specified database to a file.

        Args:
            name (str): The name of the database to back up.
            destination_file (Path): The path to the file where the backup will be stored.

        Returns:
            bool: True if the backup was successful, False otherwise.
        """
        raise Exception("Unsupported method")

    @abstractmethod
    def restore_database(self, name: str, source_file: Path) -> bool:
        """
        Restores the specified database from a backup file.

        Args:
            name (str): The name of the database to restore.
            source_file (Path): The path to the backup file.

        Returns:
            bool: True if the restore was successful, False otherwise.
        """
        raise Exception("Unsupported method")
