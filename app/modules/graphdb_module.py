import logging
from pathlib import Path
from typing import List, Optional

import requests
from requests.auth import HTTPBasicAuth

from app.modules.abstract_module import AbstractModule

logger = logging.getLogger(__name__)


class GraphDBModule(AbstractModule):
    """
    Adapter REST per Ontotext GraphDB.

    End-points usati (≥ 9.4):
      • GET  /rest/repositories
      • POST /rest/recovery/backup/{id}
      • GET  /rest/recovery/download/{file}
      • POST /rest/recovery/restore/{id}
    """

    def __init__(
        self,
        host: str,
        port: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        maintenance_db: str = "", # Ignored by GraphDBModule, kept for super() compatibility
        timeout: int = 60,
    ):
        """
        Initializes the GraphDBModule with connection details and API settings.

        Args:
            host (str): The hostname or IP address of the GraphDB server.
            port (str): The port number of the GraphDB server.
            username (Optional[str]): The username for GraphDB authentication.
            password (Optional[str]): The password for GraphDB authentication.
            maintenance_db (str): Not used by GraphDB, kept for compatibility with AbstractModule.
            timeout (int): Timeout in seconds for HTTP requests to GraphDB.
        """
        super().__init__(host, port, username, password, maintenance_db or "")
        self._base = f"http://{self._host}:{self._port}"
        self._auth = HTTPBasicAuth(username, password) if username and password else None
        self._timeout = timeout

    #helper HTTP
    def _get(self, path: str, **kw) -> requests.Response:
        url = f"{self._base}{path}"
        r = requests.get(url, auth=self._auth, timeout=self._timeout, **kw)
        r.raise_for_status()
        return r

    def _post(self, path: str, **kw) -> requests.Response:
        url = f"{self._base}{path}"
        r = requests.post(url, auth=self._auth, timeout=self._timeout, **kw)
        r.raise_for_status()
        return r

    #public API
    def list_all_databases(self) -> List[str]:
        """
        Lists all repository IDs present on the GraphDB server.

        Returns:
            List[str]: A list of repository IDs. Returns an empty list on failure.
        """
        try:
            data = self._get("/rest/repositories").json()
            return [repo["id"] for repo in data if isinstance(repo, dict) and "id" in repo]
        except requests.exceptions.RequestException as exc:
            logger.error(f"Failed to retrieve repository list from GraphDB: {exc}")
            return []
        except Exception as exc:
            logger.error(f"An unexpected error occurred while listing GraphDB repositories: {exc}")
            return []

    def backup_database(self, name: str, destination_file: Path) -> bool:
        """
        Creates a backup of the specified GraphDB repository and saves it as a ZIP file.

        Args:
            name (str): The ID of the GraphDB repository to back up.
            destination_file (Path): The full path where the backup ZIP file will be saved.

        Returns:
            bool: True if the backup was successful, False otherwise.
        """
        try:
            logger.info(f"Starting backup for GraphDB repository '{name}'...")
            r = self._post(f"/rest/recovery/backup/{name}")
            backup_file_name_on_server = r.text.strip().strip('"')
            logger.info(f"Backup process for '{name}' initiated on server, server-side backup file: '{backup_file_name_on_server}'. Downloading...")

            destination_file.parent.mkdir(parents=True, exist_ok=True)
            with self._get(f"/rest/recovery/download/{backup_file_name_on_server}", stream=True) as download_stream:
                with destination_file.open("wb") as f_out:
                    for chunk in download_stream.iter_content(chunk_size=8192): # Adjusted chunk_size
                        f_out.write(chunk)

            logger.info(f"Backup for repository '{name}' successfully saved to {destination_file}")
            return True
        except requests.exceptions.RequestException as exc:
            logger.error(f"GraphDB backup for repository '{name}' failed during HTTP operation: {exc}")
            return False
        except Exception as exc:
            logger.error(f"An unexpected error occurred during GraphDB backup for '{name}': {exc}")
            return False

    def restore_database(self, name: str, source_file: Path) -> bool:
        """
        Restores a GraphDB repository from a backup ZIP file.

        Args:
            name (str): The ID of the GraphDB repository to restore.
            source_file (Path): The path to the backup ZIP file.

        Returns:
            bool: True if the restore was successful, False otherwise.
        """
        if not source_file.exists():
            logger.error(f"Backup file {source_file} does not exist for GraphDB restore.")
            return False

        try:
            logger.info(f"Starting restore for GraphDB repository '{name}' from file {source_file}...")
            with source_file.open("rb") as f_in:
                files_payload = {"file": (source_file.name, f_in, "application/zip")}
                self._post(f"/rest/recovery/restore/{name}", files=files_payload)
            logger.info(f"Repository '{name}' successfully restored from {source_file}")
            return True
        except requests.exceptions.RequestException as exc:
            logger.error(f"GraphDB restore for repository '{name}' failed during HTTP operation: {exc}")
            return False
        except Exception as exc:
            logger.error(f"An unexpected error occurred during GraphDB restore for '{name}': {exc}")
            return False
