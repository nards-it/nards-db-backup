import gzip
import logging
import shutil
from abc import ABCMeta, abstractmethod
from pathlib import Path

import List

# Configura il logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class UnsupportedMethod(Exception):
    """Exception raised for custom error scenarios."""

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class AbstractModule(metaclass=ABCMeta):
    """
    Abstract base class for a database module, providing methods for listing,
    backing up, and restoring databases.
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
        Initializes the database module with connection details.

        Args:
            host (str): The hostname of the database server.
            port (str): The port number of the database server.
            username (str): The username to connect to the database.
            password (str): The password to connect to the database.
            maintenance_db (str): The name of the database used for maintenance.
            file_extension (str): Extension used for generated backup files.
        """
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._maintenance_db = maintenance_db
        if not file_extension.startswith(".") or file_extension == ".":
            raise ValueError("Backup file extension must start with a dot.")
        self._file_extension = file_extension

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
        raise UnsupportedMethod("list_all_databases")

    def backup_database(self, name: str, destination_file: Path) -> bool:
        """Create a backup, applying gzip when its destination ends in ``.gz``."""
        destination_path = Path(destination_file)
        uncompressed_path = (
            destination_path.with_suffix("")
            if destination_path.name.endswith(".gz")
            else destination_path
        )
        success = self._backup_database(name, uncompressed_path)
        if not success or not destination_path.name.endswith(".gz"):
            return success

        try:
            self.compress_backup(uncompressed_path)
            return True
        except OSError as exc:
            logger.error(f"Error compressing backup '{uncompressed_path}': {exc}")
            return False

    @abstractmethod
    def _backup_database(self, name: str, destination_file: Path) -> bool:
        """Implement the database-specific uncompressed backup operation."""
        raise UnsupportedMethod("_backup_database")

    def restore_database(self, name: str, source_file: Path) -> bool:
        """Restore a backup, transparently expanding gzip files when required."""
        source_path = Path(source_file)
        temporary_file = False
        if source_path.name.endswith(".gz"):
            try:
                source_path = self.decompress_backup(source_path)
                temporary_file = True
            except (OSError, ValueError) as exc:
                logger.error(
                    f"Unable to prepare backup '{source_file}' for restore: {exc}"
                )
                return False

        try:
            return self._restore_database(name, source_path)
        finally:
            if temporary_file and source_path.exists():
                source_path.unlink()

    @abstractmethod
    def _restore_database(self, name: str, source_file: Path) -> bool:
        """Implement the database-specific uncompressed restore operation.

        Args:
            name (str): The name of the database to restore.
            source_file (Path): The path to the backup file.

        Returns:
            bool: True if the restore was successful, False otherwise.
        """
        raise UnsupportedMethod("_restore_database")

    def backup_file_name(self, database_name: str, timestamp: str) -> str:
        """Return the standard name for a backup produced at ``timestamp``."""
        return f"{database_name}.{timestamp}{self.file_extension}"

    def backup_file_glob(self, database_name: str | None = None) -> str:
        """Return the glob used to find this module's backup files."""
        database_pattern = f"{database_name}.*" if database_name else "*"
        return f"**/{database_pattern}{self.file_extension}"

    def database_name_from_backup(self, backup_file: Path | str) -> str:
        """Extract the database name from a scheduler-generated backup file."""
        filename = Path(backup_file).name
        filename = filename.removesuffix(".gz")
        return filename.rsplit(".", 2)[0]

    def compress_backup(self, backup_file: Path | str) -> Path:
        """Compress a backup and remove its uncompressed source file.

        Args:
            backup_file: Path of the uncompressed backup.

        Returns:
            The path of the generated ``.gz`` file.
        """
        backup_path = Path(backup_file)
        gz_file = Path(f"{backup_path}.gz")
        logger.info(f"Compressing backup file {backup_file} to {gz_file}")
        with backup_path.open("rb") as f_in, gzip.open(gz_file, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        backup_path.unlink()
        logger.info("Successfully compressed and removed the uncompressed backup file.")
        return gz_file

    def decompress_backup(self, gz_file: Path | str) -> Path:
        """Decompress a ``.gz`` backup and return the restored file path.

        The compressed source file is deliberately retained, so it can remain in
        the backup archive after a restore.
        """
        gz_path = Path(gz_file)
        if gz_path.suffix != ".gz":
            raise ValueError(f"Compressed backup must have a .gz extension: {gz_path}")

        backup_file = gz_path.with_suffix("")
        logger.info(f"Decompressing backup file {gz_file} to {backup_file}")
        with gzip.open(gz_path, "rb") as f_in, backup_file.open("wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        logger.info(f"Successfully decompressed backup file to {backup_file}.")
        return backup_file
