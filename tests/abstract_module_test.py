from pathlib import Path

import pytest

from app.modules.abstract_module import AbstractModule


class _ConcreteModule(AbstractModule):
    """Minimal implementation used to exercise AbstractModule helpers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.backup_destinations = []
        self.restore_sources = []

    def list_all_databases(self):
        return []

    def _backup_database(self, name: str, destination_file: Path) -> bool:
        self.backup_destinations.append(destination_file)
        destination_file.write_bytes(b"backup content\x00with binary data")
        return True

    def _restore_database(self, name: str, source_file: Path) -> bool:
        self.restore_sources.append(source_file)
        assert source_file.read_bytes() == b"backup content\x00with binary data"
        return True


@pytest.mark.parametrize(
    ("file_extension", "should_compress"),
    [(".backup", False), (".backup.gz", True)],
)
def test_backup_and_restore_are_transparent_to_database_modules(
    tmp_path, file_extension, should_compress
):
    module = _ConcreteModule(
        "host", "port", "user", "password", "maintenance", file_extension
    )
    backup_file = tmp_path / f"database.20261019120000{file_extension}"
    uncompressed_file = backup_file.with_suffix("") if should_compress else backup_file

    assert module.backup_database("database", backup_file)
    assert module.backup_destinations == [uncompressed_file]
    assert backup_file.exists()
    assert uncompressed_file.exists() is not should_compress

    assert module.restore_database("database", backup_file)
    assert module.restore_sources == [uncompressed_file]
    assert uncompressed_file.exists() is not should_compress
