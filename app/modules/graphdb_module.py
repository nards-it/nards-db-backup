import json
import logging
import shutil
import tempfile
from pathlib import Path
from urllib.parse import quote

import requests
from requests.auth import HTTPBasicAuth

from app.modules.abstract_module import AbstractModule

logger = logging.getLogger(__name__)


class GraphDBModule(AbstractModule):
    """
    RDF data backup and restore for GraphDB Free using the RDF4J API.

    Repository configuration and instance-level system data are not included.
    """

    def __init__(
        self,
        host: str,
        port: str,
        username: str | None = None,
        password: str | None = None,
        maintenance_db: str = "",  # Ignored by GraphDBModule, kept for super() compatibility
        timeout: int = 60,
        file_extension: str = ".backup",
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
            file_extension (str): Extension used for generated backup files.
        """
        super().__init__(
            host, port, username, password, maintenance_db or "", file_extension
        )
        self._base = f"http://{self._host}:{self._port}"
        self._auth = (
            HTTPBasicAuth(username, password) if username and password else None
        )
        self._timeout = timeout

    # HTTP helpers
    def _get(self, path: str, **kw) -> requests.Response:
        """Send an authenticated GET request to a GraphDB endpoint.

        Args:
            path (str): Endpoint path relative to the GraphDB server.
            **kw: Additional arguments passed to ``requests.get``.

        Returns:
            requests.Response: Successful response; the caller must close it
            when requesting a streamed response.

        Raises:
            requests.RequestException: If the request or HTTP status fails.
        """
        url = f"{self._base}{path}"
        r = requests.get(url, auth=self._auth, timeout=self._timeout, **kw)
        r.raise_for_status()
        return r

    def _post(self, path: str, **kw) -> requests.Response:
        """Send an authenticated POST request to a GraphDB endpoint.

        Args:
            path (str): Endpoint path relative to the GraphDB server.
            **kw: Additional arguments passed to ``requests.post``.

        Returns:
            requests.Response: Successful response from the server.

        Raises:
            requests.RequestException: If the request or HTTP status fails.
        """
        url = f"{self._base}{path}"
        r = requests.post(url, auth=self._auth, timeout=self._timeout, **kw)
        r.raise_for_status()
        return r

    # Public API
    def list_all_databases(self) -> list[str]:
        """
        Lists all repository IDs present on the GraphDB server.

        Returns:
            list[str]: A list of repository IDs. Returns an empty list on failure.
        """
        try:
            data = self._get("/rest/repositories").json()
            return [
                repo["id"] for repo in data if isinstance(repo, dict) and "id" in repo
            ]
        except requests.exceptions.RequestException as exc:
            logger.error(f"Failed to retrieve repository list from GraphDB: {exc}")
            return []
        except Exception as exc:  # Catch other unexpected errors  # noqa: BLE001
            logger.error(
                f"An unexpected error occurred while listing GraphDB repositories: {exc}"
            )
            return []

    def _backup_database(self, name: str, destination_file: Path) -> bool:
        """Export a repository's explicit RDF statements as N-Quads.

        The export includes blank nodes and named graphs, but excludes inferred
        statements, repository configuration and instance-level system data.
        It streams into a temporary file before replacing the destination.

        Args:
            name (str): ID of the GraphDB repository to back up.
            destination_file (Path): Path for the resulting N-Quads file.

        Returns:
            bool: True if the export and replacement succeed; False on a
            handled HTTP or filesystem error.
        """
        repository = quote(name, safe="")
        temporary_path = None
        try:
            destination_file.parent.mkdir(parents=True, exist_ok=True)
            with (
                self._get(
                    f"/repositories/{repository}/statements",
                    params={"infer": "false"},
                    headers={"Accept": "application/n-quads"},
                    stream=True,
                ) as response,
                tempfile.NamedTemporaryFile(
                    dir=destination_file.parent, prefix=".graphdb-backup-", delete=False
                ) as output,
            ):
                temporary_path = Path(output.name)
                for chunk in response.iter_content(chunk_size=65536):
                    output.write(chunk)
            temporary_path.replace(destination_file)
            return True
        except (requests.RequestException, OSError) as exc:
            logger.error("GraphDB RDF export failed for '%s': %s", name, exc)
            return False
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _restore_prepared_database(
        self, name: str, source_file: Path, archive_file: Path
    ) -> bool:
        """Restore an expanded archive, storing recovery data beside the archive.

        Args:
            name (str): ID of the repository to restore.
            source_file (Path): Path to the expanded N-Quads backup.
            archive_file (Path): Original compressed backup, whose parent is
                used for the recovery snapshot.

        Returns:
            bool: True if the requested restore succeeds; False otherwise,
            including when the previous data was successfully recovered.
        """
        return self._restore_with_recovery(name, source_file, archive_file.parent)

    def _restore_database(self, name: str, source_file: Path) -> bool:
        """Restore an uncompressed N-Quads backup to an existing repository.

        A recovery snapshot is created beside the backup before replacement.
        See ``_restore_with_recovery`` for failure and concurrency behavior.

        Args:
            name (str): ID of the repository to restore.
            source_file (Path): Path to the N-Quads backup.

        Returns:
            bool: True if the requested restore succeeds; False otherwise.
        """
        return self._restore_with_recovery(name, source_file, source_file.parent)

    def _restore_with_recovery(
        self, name: str, source_file: Path, recovery_parent: Path
    ) -> bool:
        """Replace RDF data after saving a snapshot for recovery.

        The snapshot and metadata are saved in a private directory under
        ``recovery_parent``. If replacement fails after modification starts,
        the method attempts to restore the snapshot. The directory is retained
        if recovery fails or execution is interrupted before cleanup.

        Replacement and recovery each clear and import in separate requests;
        they are not atomic. Other writes must be stopped throughout the
        operation, and a lost HTTP response can leave the outcome uncertain.

        Args:
            name (str): ID of the existing repository to restore.
            source_file (Path): Path to the N-Quads backup to import.
            recovery_parent (Path): Writable directory for the snapshot.

        Returns:
            bool: True only if the requested restore succeeds. Returns False
            on a handled error, even if the previous data was recovered.
        """
        recovery_dir = None
        snapshot_ready = False
        modification_started = False
        may_remove_snapshot = False
        try:
            # Fail before changing the database if the requested backup is unreadable.
            with source_file.open("rb"):
                pass
            recovery_dir = Path(
                tempfile.mkdtemp(prefix=".graphdb-recovery-", dir=recovery_parent)
            )
            (recovery_dir / "metadata.json").write_text(
                json.dumps({"repository": name, "server": self._base}), encoding="utf-8"
            )
            snapshot = recovery_dir / "previous.nq"
            if not self._backup_database(name, snapshot):
                may_remove_snapshot = True
                return False
            snapshot_ready = True
            logger.info("GraphDB recovery snapshot for '%s': %s", name, snapshot)

            modification_started = True
            self._replace_rdf(name, source_file)
            may_remove_snapshot = True
            return True
        except (requests.RequestException, OSError, ValueError) as exc:
            logger.error("GraphDB restore failed for '%s': %s", name, exc)
            if snapshot_ready and modification_started:
                try:
                    self._replace_rdf(name, snapshot)
                except (requests.RequestException, OSError, ValueError) as recovery_exc:
                    logger.error(
                        "GraphDB recovery failed for '%s': %s. Recovery snapshot retained at %s",
                        name,
                        recovery_exc,
                        snapshot,
                    )
                else:
                    logger.warning("GraphDB previous RDF data restored for '%s'", name)
                    may_remove_snapshot = True
            elif not snapshot_ready:
                may_remove_snapshot = True
            return False
        finally:
            if recovery_dir is not None and may_remove_snapshot:
                try:
                    shutil.rmtree(recovery_dir)
                except OSError as exc:
                    logger.warning(
                        "Could not remove recovery directory %s: %s", recovery_dir, exc
                    )

    def _replace_rdf(self, name: str, source_file: Path) -> None:
        """Clear a repository and stream an N-Quads file into it.

        Clearing and importing are separate operations. The caller is
        responsible for recovery if either operation fails after clearing.

        Args:
            name (str): ID of the repository to replace.
            source_file (Path): Path to the N-Quads file to import.

        Raises:
            OSError: If the source file cannot be opened or read.
            requests.RequestException: If either HTTP request fails.
        """
        repository = quote(name, safe="")
        with source_file.open("rb") as source:
            self._post(
                f"/repositories/{repository}/statements", data={"update": "CLEAR ALL"}
            )
            self._post(
                f"/repositories/{repository}/statements",
                headers={"Content-Type": "application/n-quads"},
                data=source,
            )
