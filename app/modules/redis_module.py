import logging
import shutil
import subprocess
from pathlib import Path
from typing import List

import redis

from app.modules.abstract_module import AbstractModule

logger = logging.getLogger(__name__)


class RedisModule(AbstractModule):
    """
    Module for backing up and restoring Redis databases.
    Redis backups are typically RDB files.
    """

    def __init__(
        self,
        host: str,
        port: str,
        username: str = None,
        password: str = None,
        maintenance_db: str = None,
        container_name: str = None,
    ):
        """
        Initializes the Redis module.

        Args:
            host (str): The hostname of the Redis server.
            port (str): The port number of the Redis server.
            username (str, optional): The username for Redis (less common, for ACLs). Defaults to None.
            password (str, optional): The password for Redis. Defaults to None.
            maintenance_db (str, optional): Not strictly applicable to Redis. Defaults to None.
            container_name (str, optional): The name or ID of the Docker container running Redis.
                                            Used for `docker cp` operations if Redis is containerized. Defaults to None.
        """
        super().__init__(host, port, username, password, maintenance_db)
        # maintenance_db is not strictly applicable to Redis in the same way as SQL.
        # Username is also less common for Redis connection strings directly in redis-py prior to 6.0 if not using ACLs.
        self.redis_client = redis.Redis(
            host=self.host, port=int(self.port), password=self.password, db=0
        )  # Assuming db 0 for operations
        self.container_name = container_name  # Used for docker cp operations

    def _get_rdb_config(self) -> tuple[Path, str]:
        """
        Gets the RDB directory and filename from Redis config.
        Returns:
            tuple[Path, str]: (Path(directory), filename)
        """
        try:
            rdb_directory_str = self.redis_client.config_get("dir").get("dir")
            rdb_filename_str = self.redis_client.config_get("dbfilename").get(
                "dbfilename"
            )
            if not rdb_directory_str or not rdb_filename_str:
                logger.warning(
                    "Could not retrieve RDB dir/filename from Redis config. Falling back to defaults."
                )
                return Path("/data"), "dump.rdb"  # Common defaults
            return Path(rdb_directory_str), rdb_filename_str
        except redis.exceptions.RedisError as e:
            logger.error(
                f"Error getting RDB config from Redis: {e}. Falling back to defaults."
            )
            return Path("/data"), "dump.rdb"  # Fallback

    def _find_container_by_mapped_port(self, host_port: int) -> str | None:
        """
        Best-effort detection of the Redis container name by inspecting docker ps
        and matching the published port mapping "*:host_port->6379/tcp".

        Args:
            host_port (int): The host port where Redis is reachable (DB_PORT).

        Returns:
            Optional[str]: The container name (or ID) if detected, else None.
        """
        try:
            result = subprocess.run(
                [
                    "docker",
                    "ps",
                    "--format",
                    "{{.ID}} {{.Names}} {{.Ports}}",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            lines = result.stdout.strip().splitlines()
            token = f":{host_port}->6379"
            for line in lines:
                parts = line.split(" ", 2)
                if len(parts) < 3:
                    continue
                cid, name, ports = parts[0], parts[1], parts[2]
                if token in ports:
                    return name or cid
        except Exception as e:
            logger.debug(f"Could not detect Redis container by port {host_port}: {e}")
        return None

    def list_all_databases(self) -> List[str]:
        """
        Lists all "databases" in Redis.
        For Redis, this typically means the single dataset or configured databases.
        We'll return a placeholder as Redis doesn't have named databases like SQL.
        """
        try:
            self.redis_client.ping()
            # Could try to get info about databases if needed, e.g., self.redis_client.info('keyspace')
            # For simplicity, we return a generic name.
            return ["redis_data"]
        except redis.exceptions.ConnectionError as e:
            logger.error(f"Could not connect to Redis to list databases: {e}")
            return []

    def backup_database(self, name: str, destination_file: Path) -> bool:
        """
        Backs up the Redis database (RDB snapshot).
        The 'name' parameter is mostly a placeholder for Redis as we backup the whole instance.

        Args:
            name (str): Name of the "database" (ignored for Redis RDB backup).
            destination_file (Path): The path to the file where the backup will be stored.

        Returns:
            bool: True if the backup was successful, False otherwise.
        """
        logger.info(f"Starting Redis backup for '{name}' to '{destination_file}'...")
        try:
            # Ensure destination directory exists
            destination_file.parent.mkdir(parents=True, exist_ok=True)

            # Using SAVE for synchronous operation.
            logger.info("Executing SAVE on Redis server (this will block Redis)...")
            self.redis_client.save()
            logger.info("SAVE command completed.")

            rdb_dir_internal, rdb_filename_internal = self._get_rdb_config()
            # Paths: host-visible (for direct copy) vs container path (for docker cp fallback)
            import os as _os

            host_dir_override = _os.environ.get("REDIS_RDB_HOST_DIR")
            rdb_path_host = (
                Path(host_dir_override) / rdb_filename_internal
                if host_dir_override and not self.container_name
                else rdb_dir_internal / rdb_filename_internal
            )
            rdb_path_container = rdb_dir_internal / rdb_filename_internal

            if self.container_name:
                logger.info(
                    f"Attempting to copy RDB file from container '{self.container_name}:{rdb_path_container}' to host '{destination_file}'"
                )
                try:
                    # It's better to ensure the file exists in container first, but that's harder without `docker exec`
                    # We assume SAVE worked and the file is at the configured path inside the container.
                    copy_command = [
                        "docker",
                        "cp",
                        f"{self.container_name}:{rdb_path_container}",
                        str(destination_file),
                    ]
                    process = subprocess.run(
                        copy_command, capture_output=True, text=True, check=True
                    )
                    logger.info(
                        f"Successfully copied RDB file from container. stdout: {process.stdout}"
                    )
                except subprocess.CalledProcessError as e:
                    logger.error(
                        f"Failed to copy RDB file from container: {e}. stderr: {e.stderr}, stdout: {e.stdout}"
                    )
                    return False
                except FileNotFoundError:
                    logger.error(
                        "`docker` command not found. Cannot copy RDB file from container."
                    )
                    return False
            else:
                # Logic for non-containerized Redis (or if container_name is not provided)
                # This assumes Redis is reachable on host and we have direct access to its RDB file path.
                logger.info(
                    f"Copying RDB file from local Redis path '{rdb_path_host}' to '{destination_file}'..."
                )
                try:
                    if not rdb_path_host.exists():
                        logger.error(
                            f"Local RDB file not found at '{rdb_path_host}'. Backup failed."
                        )
                        return False
                    shutil.copy(str(rdb_path_host), str(destination_file))
                except PermissionError:
                    # Fallback: attempt docker cp by detecting the container via published port
                    logger.warning(
                        "Permission denied accessing local RDB file. Attempting docker cp fallback by detecting Redis container."
                    )
                    detected = self._find_container_by_mapped_port(int(self.port))
                    if not detected:
                        logger.error(
                            "Unable to detect Redis container for docker cp fallback."
                        )
                        return False
                    try:
                        copy_command = [
                            "docker",
                            "cp",
                            f"{detected}:{rdb_path_container}",
                            str(destination_file),
                        ]
                        process = subprocess.run(
                            copy_command, capture_output=True, text=True, check=True
                        )
                        logger.info(
                            f"Successfully copied RDB file from detected container '{detected}'. stdout: {process.stdout}"
                        )
                    except subprocess.CalledProcessError as e:
                        logger.error(
                            f"Failed docker cp from detected container '{detected}': {e}. stderr: {e.stderr}, stdout: {e.stdout}"
                        )
                        return False
                    except FileNotFoundError:
                        logger.error(
                            "`docker` command not found. Cannot perform docker cp fallback."
                        )
                        return False

            logger.info(
                f"Redis backup for '{name}' completed successfully to '{destination_file}'."
            )
            return True
        except redis.exceptions.RedisError as e:
            logger.error(f"Redis error during backup: {e}")
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred during Redis backup: {e}")
            return False

    def restore_database(self, name: str, source_file: Path) -> bool:
        """
        Restores the Redis database from an RDB backup file.
        The 'name' parameter is mostly a placeholder.

        Args:
            name (str): Name of the "database" (ignored for Redis RDB restore).
            source_file (Path): The path to the backup file.

        Returns:
            bool: True if the restore was successful, False otherwise.
        """
        logger.info(f"Starting Redis restore for '{name}' from '{source_file}'...")
        if not source_file.exists():
            logger.error(f"Backup file '{source_file}' not found. Restore failed.")
            return False

        try:
            rdb_dir_internal, rdb_filename_internal = self._get_rdb_config()
            import os as _os

            host_dir_override = _os.environ.get("REDIS_RDB_HOST_DIR")
            rdb_path_host = (
                Path(host_dir_override) / rdb_filename_internal
                if host_dir_override and not self.container_name
                else rdb_dir_internal / rdb_filename_internal
            )
            rdb_path_container = rdb_dir_internal / rdb_filename_internal

            dest_desc = None
            if self.container_name:
                logger.info(
                    f"Attempting to copy backup file '{source_file}' to container '{self.container_name}:{rdb_path_container}'"
                )
                try:
                    # Ensure parent directory exists in container (docker cp doesn't create it by default for the file path)
                    # This might require `docker exec <container> mkdir -p <dir>` if not already present.
                    # For simplicity, we assume the directory configured in Redis exists.
                    copy_command = [
                        "docker",
                        "cp",
                        str(source_file),
                        f"{self.container_name}:{rdb_path_container}",
                    ]
                    process = subprocess.run(
                        copy_command, capture_output=True, text=True, check=True
                    )
                    logger.info(
                        f"Successfully copied RDB file to container. stdout: {process.stdout}"
                    )
                    dest_desc = str(rdb_path_container)
                except subprocess.CalledProcessError as e:
                    logger.error(
                        f"Failed to copy RDB file to container: {e}. stderr: {e.stderr}, stdout: {e.stdout}"
                    )
                    return False
                except FileNotFoundError:
                    logger.error(
                        "`docker` command not found. Cannot copy RDB file to container."
                    )
                    return False
            else:
                # Logic for non-containerized Redis
                logger.info(
                    f"Copying backup file '{source_file}' to local Redis RDB path '{rdb_path_host}'..."
                )
                try:
                    rdb_path_host.parent.mkdir(
                        parents=True, exist_ok=True
                    )  # Ensure local dir exists
                    shutil.copy(str(source_file), str(rdb_path_host))
                    dest_desc = str(rdb_path_host)
                except PermissionError:
                    # Fallback: attempt docker cp by detecting the container via published port
                    logger.warning(
                        "Permission denied writing local RDB file. Attempting docker cp fallback by detecting Redis container."
                    )
                    detected = self._find_container_by_mapped_port(int(self.port))
                    if not detected:
                        logger.error(
                            "Unable to detect Redis container for docker cp fallback."
                        )
                        return False
                    try:
                        copy_command = [
                            "docker",
                            "cp",
                            str(source_file),
                            f"{detected}:{rdb_path_container}",
                        ]
                        process = subprocess.run(
                            copy_command, capture_output=True, text=True, check=True
                        )
                        logger.info(
                            f"Successfully copied RDB file to detected container '{detected}'. stdout: {process.stdout}"
                        )
                        dest_desc = str(rdb_path_container)
                    except subprocess.CalledProcessError as e:
                        logger.error(
                            f"Failed docker cp to detected container '{detected}': {e}. stderr: {e.stderr}, stdout: {e.stdout}"
                        )
                        return False
                    except FileNotFoundError:
                        logger.error(
                            "`docker` command not found. Cannot perform docker cp fallback."
                        )
                        return False

            if dest_desc is None:
                dest_desc = "<unknown>"
            logger.info(
                f"Redis RDB file '{source_file}' copied to target location '{dest_desc}'."
            )
            logger.info(
                "A Redis server restart is required to load the restored RDB file."
            )
            # The module itself won't try to reload or restart Redis. This should be handled by the caller.
            return True
        except redis.exceptions.RedisError as e:
            logger.error(f"Redis error during restore: {e}")
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred during Redis restore: {e}")
            return False
