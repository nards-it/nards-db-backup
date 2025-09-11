import os
import socket
import pytest


@pytest.fixture(scope="session")
def docker_compose_file(pytestconfig):
    """Point pytest-docker to the test docker-compose file."""
    return os.path.join(str(pytestconfig.rootdir), "tests", "docker-compose.yml")


@pytest.fixture(scope="session")
def docker_compose_command():
    """Pick the Compose command available in the environment."""
    import shutil

    if shutil.which("docker"):
        return "docker compose"
    if shutil.which("docker-compose"):
        return "docker-compose"
    # Fallback to the modern default
    return "docker compose"


@pytest.fixture(scope="session", autouse=True)
def ensure_services_for_local(request):
    """
    For local runs: if DB_* env vars are not set, start test DBs via docker-compose
    and export the expected environment variables for tests. In CI, env vars are
    already set by the test-runner, so this fixture becomes a no-op.
    """

    # If CI or env vars already provided, do nothing
    if (
        os.environ.get("DB_HOST_MYSQL")
        and os.environ.get("DB_HOST_POSTGRES")
        and os.environ.get("DB_HOST_POSTGIS")
        and os.environ.get("DB_HOST_REDIS")
        and os.environ.get("DB_HOST_MONGODB")
    ):
        # Yield to satisfy generator fixture contract
        yield
        return

    # Get docker_services fixture only when needed
    docker_services = request.getfixturevalue("docker_services")

    # Resolve published ports for local Docker engine
    mysql_port = docker_services.port_for("mysql", 3306)
    pg_port = docker_services.port_for("postgres", 5432)
    postgis_port = docker_services.port_for("postgis", 5432)
    redis_port = docker_services.port_for("redis", 6379)
    mongodb_port = docker_services.port_for("mongodb", 27017)

    # Export env vars consumed by tests
    os.environ.setdefault("DB_HOST_MYSQL", "127.0.0.1")
    os.environ.setdefault("DB_PORT_MYSQL", str(mysql_port))
    os.environ.setdefault("DB_USER_MYSQL", "test_user")
    os.environ.setdefault("DB_PASSWORD_MYSQL", "test_password")
    os.environ.setdefault("DB_NAME_MYSQL", "test_database")

    os.environ.setdefault("DB_HOST_POSTGRES", "127.0.0.1")
    os.environ.setdefault("DB_PORT_POSTGRES", str(pg_port))
    os.environ.setdefault("DB_USER_POSTGRES", "test_user")
    os.environ.setdefault("DB_PASSWORD_POSTGRES", "test_password")
    os.environ.setdefault("DB_NAME_POSTGRES", "test_database")

    os.environ.setdefault("DB_HOST_POSTGIS", "127.0.0.1")
    os.environ.setdefault("DB_PORT_POSTGIS", str(postgis_port))
    os.environ.setdefault("DB_USER_POSTGIS", "test_user")
    os.environ.setdefault("DB_PASSWORD_POSTGIS", "test_password")
    os.environ.setdefault("DB_NAME_POSTGIS", "test_database")

    os.environ.setdefault("MYSQL_SSL_MODE", "DISABLED")
    os.environ.setdefault("PG_RESTORE_CLEAN", "true")

    # Redis env for tests
    os.environ.setdefault("DB_HOST_REDIS", "127.0.0.1")
    os.environ.setdefault("DB_PORT_REDIS", str(redis_port))
    os.environ.setdefault("DB_PASSWORD_REDIS", "")
    # Host path to the Redis RDB directory bind-mounted in tests/docker-compose.yml
    try:
        root = str(request.config.rootdir)
    except Exception:
        root = os.getcwd()
    os.environ.setdefault(
        "REDIS_RDB_HOST_DIR", os.path.join(root, "tests", "redis-data")
    )

    # MongoDB env for tests
    os.environ.setdefault("DB_HOST_MONGODB", "127.0.0.1")
    os.environ.setdefault("DB_PORT_MONGODB", str(mongodb_port))
    os.environ.setdefault("DB_USER_MONGODB", "testuser")
    os.environ.setdefault("DB_PASSWORD_MONGODB", "testpassword")
    os.environ.setdefault("DB_NAME_MONGODB", "admin")

    # Simple TCP readiness checks
    def _tcp_ready(host: str, port: int) -> bool:
        with socket.socket() as s:
            s.settimeout(1.0)
            return s.connect_ex((host, port)) == 0

    docker_services.wait_until_responsive(
        timeout=120, pause=2, check=lambda: _tcp_ready("127.0.0.1", mysql_port)
    )
    docker_services.wait_until_responsive(
        timeout=120, pause=2, check=lambda: _tcp_ready("127.0.0.1", pg_port)
    )
    docker_services.wait_until_responsive(
        timeout=120, pause=2, check=lambda: _tcp_ready("127.0.0.1", postgis_port)
    )
    docker_services.wait_until_responsive(
        timeout=120, pause=2, check=lambda: _tcp_ready("127.0.0.1", redis_port)
    )
    docker_services.wait_until_responsive(
        timeout=150, pause=2, check=lambda: _tcp_ready("127.0.0.1", mongodb_port)
    )

    # Yield to tests; docker_services handles teardown automatically
    yield


import pytest


@pytest.fixture(scope="session")
def docker_compose_command():
    """Forces pytest-docker to use docker-compose (with hyphen)"""
    return "docker-compose"
