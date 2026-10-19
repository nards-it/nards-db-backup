import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PostgreSQLClientMixin:
    """Select PostgreSQL command-line clients matching the connected server."""

    _POSTGRES_CLIENT_ROOT = Path("/usr/lib/postgresql")

    def _postgres_client(self, executable: str) -> str:
        """Return the installed client executable matching the server major version."""
        if executable not in {"pg_dump", "pg_restore", "psql"}:
            raise ValueError(f"Unsupported PostgreSQL client executable: {executable}")

        major = self._postgres_server_major()
        available_majors = self._installed_postgres_majors()
        if major not in available_majors:
            raise RuntimeError(
                f"PostgreSQL server major version {major} is unsupported; "
                f"installed client versions are: {', '.join(map(str, available_majors)) or 'none'}."
            )

        client = self._postgres_client_path(major, executable)
        if not client.is_file():
            raise RuntimeError(
                f"PostgreSQL {major} client executable is not installed: {client}"
            )
        return str(client)

    def _postgres_server_major(self) -> int:
        """Return and cache the server major version reported by libpq."""
        cached_major = getattr(self, "_postgres_server_major_version", None)
        if cached_major is not None:
            return cached_major

        connection = self._connect()
        if connection is None:
            raise RuntimeError(
                "Unable to connect to PostgreSQL to determine its version."
            )
        try:
            major = connection.server_version // 10000
        finally:
            connection.close()

        self._postgres_server_major_version = major
        logger.info("Detected PostgreSQL server major version %s.", major)
        return major

    @classmethod
    def _installed_postgres_majors(cls) -> list[int]:
        """Discover PostgreSQL client versions installed in the runtime image."""
        if not cls._POSTGRES_CLIENT_ROOT.is_dir():
            return []
        return sorted(
            int(path.name)
            for path in cls._POSTGRES_CLIENT_ROOT.iterdir()
            if path.is_dir() and path.name.isdigit()
        )

    @classmethod
    def _postgres_client_path(cls, major: int, executable: str) -> Path:
        return cls._POSTGRES_CLIENT_ROOT / str(major) / "bin" / executable
