import os
import sys
import pytest
import time
from pymongo import MongoClient
from pathlib import Path
from app.modules.mongodb_module import MongoDBModule

# Add project root to the path to import application modules
sys.path.insert(1, os.getcwd())

@pytest.fixture(scope="session")
def docker_compose_file(pytestconfig):
    """Get an absolute path to the docker-compose.yml file for tests."""
    return os.path.join(str(pytestconfig.rootdir), "tests", "docker-compose.yml")

def check_mongo_connection(host, port, user, password):
    """Checks if MongoDB is ready for connections."""
    print(f"Checking MongoDB connection to {host}:{port}")
    try:
        # Connect specifying authSource=admin, as credentials are root-level.
        # The database in the URI here is less important for a ping, but 'admin' is a safe choice.
        uri = f"mongodb://{user}:{password}@{host}:{port}/admin?authSource=admin"
        client = MongoClient(uri, serverSelectionTimeoutMS=5000) # Timeout for server selection
        # The 'ping' command is a lightweight way to verify connection and authentication.
        client.admin.command('ping') 
        print(f"MongoDB connection successful.")
        return True
    except Exception as e:
        print(f"MongoDB connection failed: {e}")
        return False

@pytest.fixture(scope="session", autouse=True)
def mongodb_service(docker_ip, docker_services):
    """Ensures the MongoDB service is up and responsive."""
    docker_port = docker_services.port_for("mongodb", 27017) # Service name and internal port
    print(f"MongoDB service exposed on {docker_ip}:{docker_port}")
    
    # Wait until MongoDB is responsive
    docker_services.wait_until_responsive(
        timeout=120.0, # Increased timeout to allow MongoDB to initialize
        pause=1.0,    # Longer pause between attempts
        check=lambda: check_mongo_connection(
            host=docker_ip, 
            port=docker_port, 
            user="testuser", # User defined in docker-compose.yml for mongodb
            password="testpassword"  # Password defined in docker-compose.yml for mongodb
        )
    )
    print("MongoDB service is responsive.")
    # No need to return anything here; the fixture just waits for the service.

@pytest.fixture
def mongodb_client(docker_ip, docker_services):
    """Provides a connected MongoDB client for tests and creates test data."""
    docker_port = docker_services.port_for("mongodb", 27017)
    client = MongoClient(f"mongodb://testuser:testpassword@{docker_ip}:{docker_port}/test_db_module?authSource=admin")
    
    # Create test data
    db = client["test_db_module"] # Database specific to this test
    db.test_collection.insert_one({"key": "Original Data", "module_test": True})
    
    yield client
    
    # Cleanup: drop the module-specific test database
    client.drop_database("test_db_module")
    client.close()


@pytest.fixture
def mongodb_module(docker_ip, docker_services):
    """Instantiates the MongoDBModule for testing."""
    docker_port = docker_services.port_for("mongodb", 27017)
    # 'admin' is often used as the maintenance_db for authentication in MongoDB
    return MongoDBModule(docker_ip, str(docker_port), "testuser", "testpassword", "admin")


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
    db_name_to_test = "test_db_module" # Database created by mongodb_client
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
        assert backup_result, f"Backup failed. Check logs. Command was for {backup_file}"
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
        assert restored_data["key"] == "Original Data", "Restored data does not match original data."

    finally:
        # Cleanup backup file and directory
        if backup_file.exists():
            os.remove(backup_file)
        if backup_dir.exists():
            # Remove temporary files and then the directory if empty
            for f in backup_dir.iterdir(): os.remove(f) # Ensures directory is empty before rmdir
            backup_dir.rmdir()
