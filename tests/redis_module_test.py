import os
import sys
import time

# insert root directory into python module search path
sys.path.insert(1, os.getcwd())

import pytest
from pathlib import Path
import redis
from app.modules.redis_module import RedisModule


def _check_redis_connection(host, port, password=None):
    try:
        r = redis.Redis(
            host=host, port=int(port), password=password, socket_connect_timeout=1
        )
        r.ping()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def redis_env(pytestconfig):
    host = os.environ.get("DB_HOST_REDIS")
    port = os.environ.get("DB_PORT_REDIS")
    password = os.environ.get("DB_PASSWORD_REDIS") or None
    rdb_host_dir = os.environ.get("REDIS_RDB_HOST_DIR")
    assert host and port, "Redis env not configured (DB_HOST_REDIS/DB_PORT_REDIS)."
    # Wait until responsive (works in both CI and local)
    deadline = time.time() + 60
    while time.time() < deadline and not _check_redis_connection(host, port, password):
        time.sleep(0.5)
    assert _check_redis_connection(host, port, password), "Redis not responsive in time"
    client = redis.Redis(host=host, port=int(port), password=password)
    yield {
        "host": host,
        "port": port,
        "password": password,
        "rdb_host_dir": rdb_host_dir,
        "client": client,
    }
    try:
        client.flushall()
    except Exception:
        pass


@pytest.fixture
def redis_module(redis_env):
    return RedisModule(
        host=redis_env["host"],
        port=str(redis_env["port"]),
        password=redis_env["password"],
        container_name=None,
    )


def test_list_all_databases(redis_module, redis_env):
    assert redis_env["client"].ping()
    databases = redis_module.list_all_databases()
    assert "redis_data" in databases


def test_backup_and_restore_database(pytestconfig, redis_module, redis_env):
    assert redis_env["client"].ping()

    backup_dir = Path(str(pytestconfig.rootdir)) / "tests" / "redis_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_file = backup_dir / "test_redis_backup.rdb"
    if backup_file.exists():
        os.remove(backup_file)

    client = redis_env["client"]

    try:
        # 1. Seed data
        client.set("testkey1", "OriginalValue1")
        client.set("testkey2", "OriginalValue2")
        assert client.get("testkey1").decode("utf-8") == "OriginalValue1"

        # Disable auto-save points (SAVE command still works)
        client.config_set("save", "")

        # 2. Backup
        assert redis_module.backup_database("redis_data", backup_file)
        assert backup_file.exists()

        # 3. Modify data
        client.set("testkey1", "AlteredValue1")
        client.delete("testkey2")
        client.set("testkey3", "NewValue3")
        assert client.get("testkey1").decode("utf-8") == "AlteredValue1"
        assert client.get("testkey2") is None

        # 4. Restore to RDB path (shared volume/host dir)
        time.sleep(0.5)
        assert redis_module.restore_database("redis_data", backup_file)

        # 5. Restart Redis by SHUTDOWN NOSAVE; rely on restart policy
        try:
            client.execute_command("SHUTDOWN", "NOSAVE")
        except Exception:
            # Connection drop expected
            pass

        # Wait for Redis to come back
        host, port, password = (
            redis_env["host"],
            redis_env["port"],
            redis_env["password"],
        )
        deadline = time.time() + 60
        while time.time() < deadline and not _check_redis_connection(
            host, port, password
        ):
            time.sleep(0.5)
        assert _check_redis_connection(host, port, password), (
            "Redis did not restart in time"
        )

        reconnected = redis.Redis(host=host, port=int(port), password=password)
        time.sleep(0.5)
        assert reconnected.get("testkey1").decode("utf-8") == "OriginalValue1"
        assert reconnected.get("testkey2").decode("utf-8") == "OriginalValue2"
        assert reconnected.get("testkey3") is None

    finally:
        if backup_file.exists():
            os.remove(backup_file)
        if backup_dir.exists() and not any(backup_dir.iterdir()):
            os.rmdir(backup_dir)
        try:
            client.config_set("save", "900 1 300 10 60 10000")
            client.flushall()
        except Exception:
            pass
