import os
import sys
import time

# insert root directory into python module search path
sys.path.insert(1, os.getcwd())

import pytest
from pathlib import Path
import redis
from app.modules.redis_module import RedisModule

@pytest.fixture(scope="session")
def docker_compose_file(pytestconfig):
    return os.path.join(str(pytestconfig.rootdir), "tests", "docker-compose.yml")

def check_redis_connection(host, port, password=None):
    """Check if Redis server is ready for connections."""
    try:
        r = redis.Redis(host=host, port=port, password=password, socket_connect_timeout=1)
        r.ping()
        print("Redis server is ready for connections.")
        return True
    except redis.exceptions.ConnectionError:
        return False
    except redis.exceptions.TimeoutError:
        return False


@pytest.fixture(scope='session', autouse=True)
def redis_service(docker_ip, docker_services):
    """Ensure that Redis service is up and responsive."""
    port = docker_services.port_for("redis", 6379)
    # Wait until Redis service is ready
    docker_services.wait_until_responsive(
        timeout=60.0, pause=0.5, check=lambda: check_redis_connection(docker_ip, port)
    )
    # Yield a redis client
    client = redis.Redis(host=docker_ip, port=port)
    yield client
    # Clean up all data from the current Redis database after the session.
    client.flushall()


@pytest.fixture
def redis_container_name(docker_compose_project_name):
    # Construct the default container name used by docker-compose
    return f"{docker_compose_project_name}_redis_1"

@pytest.fixture
def redis_module(docker_ip, docker_services, redis_container_name):
    port = docker_services.port_for("redis", 6379)
    # For test purposes, we don't set a password for Redis in docker-compose.yml
    return RedisModule(host=docker_ip, port=str(port), password=None, container_name=redis_container_name)

def test_list_all_databases(redis_module, redis_service):
    """Test listing 'databases' from Redis."""
    # Ensure Redis is running and accessible
    assert redis_service.ping()
    databases = redis_module.list_all_databases()
    assert "redis_data" in databases

def test_backup_and_restore_database(pytestconfig, redis_module, redis_service, docker_services):
    """Test backup and restore of Redis data."""
    # Ensure Redis is running
    assert redis_service.ping()

    # Path for the backup file
    backup_dir = Path(str(pytestconfig.rootdir)) / "tests" / "redis_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_file = backup_dir / "test_redis_backup.rdb"

    if backup_file.exists():
        os.remove(backup_file)

    try:
        # 1. Set some initial data in Redis
        redis_service.set("testkey1", "OriginalValue1")
        redis_service.set("testkey2", "OriginalValue2")
        assert redis_service.get("testkey1").decode('utf-8') == "OriginalValue1"

        # Disable RDB saving to prevent interference during test
        redis_service.config_set("save", "")

        # 2. Perform backup
        # The 'name' argument is a placeholder for Redis backup
        backup_result = redis_module.backup_database("redis_data", backup_file)
        assert backup_result
        assert backup_file.exists()

        # 3. Change data in Redis
        redis_service.set("testkey1", "AlteredValue1")
        redis_service.delete("testkey2")
        redis_service.set("testkey3", "NewValue3")
        assert redis_service.get("testkey1").decode('utf-8') == "AlteredValue1"
        assert redis_service.get("testkey2") is None

        # 4. Perform restore
        # Short precautionary delay before restore operation.
        time.sleep(0.5) # Short precautionary delay
        restore_result = redis_module.restore_database("redis_data", backup_file)
        assert restore_result

        # Restart the Redis container to load the new RDB file
        print("Restarting Redis container to load restored RDB file...")
        docker_services._docker_compose.execute("restart redis")
        
        # Wait for Redis to be responsive again after restart
        docker_services.wait_until_responsive(
            timeout=30.0, pause=0.5, check=lambda: check_redis_connection(redis_module.host, int(redis_module.port))
        )
        print("Redis container restarted and responsive.")
        time.sleep(2) # Additional delay post-restart.

        # 5. Verify original data is restored
        # Reconnect client as the connection might have dropped after restart
        reconnected_client = redis.Redis(host=redis_module.host, port=int(redis_module.port), password=redis_module.password)
        # Short delay to allow RDB loading after restart.
        time.sleep(0.5) # Short wait for RDB to load
        assert reconnected_client.get("testkey1").decode('utf-8') == "OriginalValue1"
        assert reconnected_client.get("testkey2").decode('utf-8') == "OriginalValue2"
        assert reconnected_client.get("testkey3") is None # This key should not exist after restore

    finally:
        # Clean up the backup file
        if backup_file.exists():
            os.remove(backup_file)
        # Clean up the backup directory if empty
        if backup_dir.exists() and not any(backup_dir.iterdir()):
            os.rmdir(backup_dir)
        # Clean up redis and restore default save config if possible
        try:
            redis_service.config_set("save", "900 1 300 10 60 10000") # Restore default save points
            redis_service.flushall()
        except Exception:
            pass # Ignore errors during cleanup
