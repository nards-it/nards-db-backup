import pytest

@pytest.fixture(scope="session")
def docker_compose_command():
    """Forces pytest-docker to use docker-compose (with hyphen)"""
    return "docker-compose"
