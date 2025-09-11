import os
import sys
import pytest
import time
from pymongo import MongoClient
from pathlib import Path
from app.modules.mongodb_module import MongoDBModule

# Add project root to the path to import application modules
sys.path.insert(1, os.getcwd())


def _check_mongo_connection(host: str, port: str, user: str, password: str) -> bool:
    try:
        uri = f"mongodb://{user}:{password}@{host}:{port}/admin?authSource=admin"
        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def mongodb_env():
    host = os.environ.get("DB_HOST_MONGODB")
    port = os.environ.get("DB_PORT_MONGODB")
    user = os.environ.get("DB_USER_MONGODB", "testuser")
    password = os.environ.get("DB_PASSWORD_MONGODB", "testpassword")
    assert host and port, (
        "MongoDB env not configured (DB_HOST_MONGODB/DB_PORT_MONGODB)."
    )
    deadline = time.time() + 120
    while time.time() < deadline and not _check_mongo_connection(
        host, port, user, password
    ):
        time.sleep(1.0)
    assert _check_mongo_connection(host, port, user, password), (
        "MongoDB not responsive in time"
    )
    yield {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "maintenance_db": os.environ.get("DB_NAME_MONGODB", "admin"),
    }


@pytest.fixture
def mongodb_client(mongodb_env):
    client = MongoClient(
        f"mongodb://{mongodb_env['user']}:{mongodb_env['password']}@{mongodb_env['host']}:{mongodb_env['port']}/test_db_module?authSource=admin"
    )
    # Create test data
    db = client["test_db_module"]
    db.test_collection.insert_one({"key": "Original Data", "module_test": True})
    yield client
    # Cleanup
    try:
        client.drop_database("test_db_module")
    finally:
        client.close()


@pytest.fixture
def mongodb_module(mongodb_env):
    return MongoDBModule(
        mongodb_env["host"],
        str(mongodb_env["port"]),
        mongodb_env["user"],
        mongodb_env["password"],
        mongodb_env["maintenance_db"],
    )


def test_list_all_databases(mongodb_module, mongodb_client):
    """Tests if the MongoDB module can list databases correctly."""
    # Ensure the test database created by the mongodb_client fixture is present
    # mongodb_client creates 'test_db_module'
    databases = mongodb_module.list_all_databases()
    print(f"Databases found: {databases}")
    assert "test_db_module" in databases
    # Ensure system databases are not listed
    assert "admin" not in databases
    assert "local" not in databases
    assert "config" not in databases


def test_backup_and_restore_database(pytestconfig, mongodb_client, mongodb_module):
    """Tests MongoDB backup and restore functionality."""
    db_name_to_test = "test_db_module"  # Database created by mongodb_client
    db = mongodb_client[db_name_to_test]

    # Define backup file path
    backup_dir = Path(str(pytestconfig.rootdir)) / "tests" / "backup_temp"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_file = backup_dir / "test_mongodb_backup.gz"

    if backup_file.exists():
        os.remove(backup_file)

    try:
        # 1. Verify initial data
        initial_data = db.test_collection.find_one({"module_test": True})
        assert initial_data is not None
        assert initial_data["key"] == "Original Data"

        # 2. Perform backup
        print(f"Attempting backup of '{db_name_to_test}' to '{backup_file}'")
        backup_result = mongodb_module.backup_database(db_name_to_test, backup_file)
        assert backup_result, (
            f"Backup failed. Check logs. Command was for {backup_file}"
        )
        assert backup_file.exists(), "Backup file was not created."
        assert backup_file.stat().st_size > 0, "Backup file is empty."

        # 3. Change data in the database
        db.test_collection.delete_many({})
        db.test_collection.insert_one({"key": "Modified Data", "module_test": True})
        modified_data = db.test_collection.find_one({"module_test": True})
        assert modified_data["key"] == "Modified Data"

        # 4. Restore the database
        # The database name during restore can be the same or different.
        # If it's the same, mongorestore with --drop will delete it first.
        print(f"Attempting restore of '{db_name_to_test}' from '{backup_file}'")
        restore_result = mongodb_module.restore_database(db_name_to_test, backup_file)
        assert restore_result, "Restore failed. Check logs."

        # 5. Verify original data is restored
        # Reconnect or use the same client if the connection is still valid
        # (the client in mongodb_client should still be valid).
        restored_data = db.test_collection.find_one({"module_test": True})
        assert restored_data is not None, "No data found after restore."
        assert restored_data["key"] == "Original Data", (
            "Restored data does not match original data."
        )

    finally:
        # Cleanup backup file and directory
        if backup_file.exists():
            os.remove(backup_file)
        if backup_dir.exists():
            # Remove temporary files and then the directory if empty
            for f in backup_dir.iterdir():
                os.remove(f)  # Ensures directory is empty before rmdir
            backup_dir.rmdir()
