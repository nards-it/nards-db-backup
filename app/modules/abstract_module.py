import gzip
import os
import shutil
from abc import ABCMeta, abstractmethod
from pathlib import Path
from typing import List
import logging

# Configura il logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


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
        self._file_extension = '.backup'

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
        return self._maintenance_db

    @property
    def file_extension(self) -> str:
        """
        Returns the default extension of the created file.

        Returns:
            str: The name of the default extension of the created file.
        """
        return self._file_extension

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

    def compress_backup(self, backup_file):
        """Compress the backup file using GZ compression."""
        gz_file = f"{backup_file}.gz"
        logger.info(f"Compressing backup file {backup_file} to {gz_file}")
        with open(backup_file, 'rb') as f_in:
            with gzip.open(gz_file, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        os.remove(backup_file)  # Remove the uncompressed backup file
        logger.info(f"Successfully compressed and removed the uncompressed backup file.")

    def decompress_backup(self, gz_file):
        """Decompress the GZ file to restore the original backup file."""
        backup_file = gz_file[:-3]  # Remove the .gz extension
        logger.info(f"Decompressing backup file {gz_file} to {backup_file}")
        with gzip.open(gz_file, 'rb') as f_in:
            with open(backup_file, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        logger.info(f"Successfully decompressed backup file to {backup_file}.")
        return backup_file
