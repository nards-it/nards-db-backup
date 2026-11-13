import gzip
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from app.modules.abstract_module import AbstractModule

PAYLOAD = b"backup content\x00with binary data"


def _write_gzip(path: Path, payload: bytes = PAYLOAD) -> None:
    """Write ``payload`` as a gzip archive at ``path``."""
    with gzip.open(path, "wb") as file_out:
        file_out.write(payload)


class _ConcreteModule(AbstractModule):
    """Minimal implementation used to exercise AbstractModule helpers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.backup_destinations = []
        self.restore_sources = []
        self.restore_result = True

    def list_all_databases(self):
        return []

    def _backup_database(self, name: str, destination_file: Path) -> bool:
        self.backup_destinations.append(destination_file)
        destination_file.write_bytes(PAYLOAD)
        return True

    def _restore_database(self, name: str, source_file: Path) -> bool:
        self.restore_sources.append(source_file)
        if not self.restore_result:
            return False
        assert source_file.read_bytes() == PAYLOAD
        return True


def _module(file_extension: str = ".backup") -> _ConcreteModule:
    return _ConcreteModule(
        "host", "port", "user", "password", "maintenance", file_extension
    )


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
    restored = module.restore_sources[0]
    assert restored.name == uncompressed_file.name
    assert (restored == uncompressed_file) is not should_compress
    assert not should_compress or not restored.parent.exists()
    assert uncompressed_file.exists() is not should_compress


@pytest.mark.parametrize("file_extension", [".backup", ".backup.gz"])
def test_restore_propagates_module_failure_and_removes_temp_file(
    tmp_path, file_extension
):
    """A failed module restore is reported and the archive is never removed."""
    module = _module(file_extension)
    module.restore_result = False
    backup_file = tmp_path / f"database.20261019120000{file_extension}"
    if file_extension.endswith(".gz"):
        _write_gzip(backup_file)
        decompressed_file = backup_file.with_suffix("")
    else:
        backup_file.write_bytes(PAYLOAD)
        decompressed_file = backup_file

    assert module.restore_database("database", backup_file) is False
    restored = module.restore_sources[0]
    assert restored.name == decompressed_file.name
    assert (restored == decompressed_file) is (not file_extension.endswith(".gz"))
    if file_extension.endswith(".gz"):
        assert not restored.parent.exists()
    assert backup_file.exists()
    if file_extension.endswith(".gz"):
        assert not decompressed_file.exists()


def test_restore_fails_on_corrupt_compressed_backup(tmp_path):
    """A corrupt archive must not reach the module nor leave files behind."""
    module = _module(".backup.gz")
    backup_file = tmp_path / "database.20261019120000.backup.gz"
    backup_file.write_bytes(b"this is not a gzip archive")

    assert module.restore_database("database", backup_file) is False
    assert module.restore_sources == []
    assert not (tmp_path / "database.20261019120000.backup").exists()


def test_restore_fails_if_temporary_directory_cannot_be_created(tmp_path, monkeypatch):
    module = _module(".backup.gz")
    archive = tmp_path / "database.backup.gz"
    _write_gzip(archive)

    def fail_to_create_directory(*args, **kwargs):
        raise OSError("temporary filesystem unavailable")

    monkeypatch.setattr(
        "app.modules.abstract_module.tempfile.TemporaryDirectory",
        fail_to_create_directory,
    )

    assert module.restore_database("database", archive) is False
    assert module.restore_sources == []
    assert archive.exists()


def test_restore_fails_on_truncated_compressed_backup(tmp_path):
    """A valid gzip header with a truncated body fails without residues."""
    module = _module(".backup.gz")
    backup_file = tmp_path / "database.20261019120000.backup.gz"
    _write_gzip(backup_file, PAYLOAD * 1000)
    backup_file.write_bytes(backup_file.read_bytes()[:20])

    assert module.restore_database("database", backup_file) is False
    assert module.restore_sources == []
    assert not (tmp_path / "database.20261019120000.backup").exists()


def test_restore_does_not_overwrite_existing_uncompressed_backup(tmp_path):
    """The decompressed file is isolated from the archive directory."""
    module = _module(".backup.gz")
    archive = tmp_path / "database.20261019120000.backup.gz"
    _write_gzip(archive)
    existing = tmp_path / "database.20261019120000.backup"
    existing.write_bytes(b"pre-existing backup")

    assert module.restore_database("database", archive)

    assert existing.read_bytes() == b"pre-existing backup"
    restored = module.restore_sources[0]
    assert restored.name == existing.name
    assert restored.parent != tmp_path
    assert not restored.parent.exists()
    assert archive.exists()


def test_repeated_restores_use_clean_isolated_directories(tmp_path):
    module = _module(".backup.gz")
    archive = tmp_path / "database.20261019120000.backup.gz"
    _write_gzip(archive)

    for _ in range(3):
        assert module.restore_database("database", archive)

    assert len({path.parent for path in module.restore_sources}) == 3
    assert all(not path.parent.exists() for path in module.restore_sources)
    assert list(tmp_path.iterdir()) == [archive]


def test_concurrent_restores_have_independent_temporary_files(tmp_path):
    archive = tmp_path / "database.20261019120000.backup.gz"
    _write_gzip(archive)
    barrier = Barrier(2, timeout=5)

    class ConcurrentModule(_ConcreteModule):
        def _restore_database(self, name, source_file):
            self.restore_sources.append(source_file)
            barrier.wait()
            return source_file.read_bytes() == PAYLOAD

    modules = [
        ConcurrentModule("host", "port", "user", "password", "db") for _ in range(2)
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda module: module.restore_database("database", archive), modules
            )
        )

    paths = [module.restore_sources[0] for module in modules]
    assert results == [True, True]
    assert paths[0].parent != paths[1].parent
    assert all(not path.parent.exists() for path in paths)


def test_restore_exception_cleans_temporary_directory(tmp_path):
    archive = tmp_path / "database.backup.gz"
    _write_gzip(archive)

    class FailingModule(_ConcreteModule):
        def _restore_database(self, name, source_file):
            self.restore_sources.append(source_file)
            raise RuntimeError("restore failed")

    module = FailingModule("host", "port", "user", "password", "db")
    with pytest.raises(RuntimeError, match="restore failed"):
        module.restore_database("database", archive)
    assert not module.restore_sources[0].parent.exists()
    assert archive.exists()


def test_corrupt_backup_keeps_existing_files_and_leaves_no_residue(tmp_path):
    """A corrupt archive never touches pre-existing files."""
    module = _module(".backup.gz")
    archive = tmp_path / "database.20261019120000.backup.gz"
    archive.write_bytes(b"this is not a gzip archive")
    existing = tmp_path / "database.20261019120000.backup"
    existing.write_bytes(b"pre-existing backup")

    assert module.restore_database("database", archive) is False

    assert existing.read_bytes() == b"pre-existing backup"
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "database.20261019120000.backup",
        "database.20261019120000.backup.gz",
    ]


@pytest.mark.parametrize(
    "file_extension", [".backup", ".backup.gz", ".sql.bak", ".tar.zst"]
)
@pytest.mark.parametrize("database_name", ["database", "my.database"])
def test_backup_file_name_round_trips_through_database_name_from_backup(
    file_extension, database_name
):
    """Backup names can be parsed back to the original database name."""
    module = _module(file_extension)

    backup_file = module.backup_file_name(database_name, "20261019120000")

    assert backup_file == f"{database_name}.20261019120000{file_extension}"
    assert module.database_name_from_backup(backup_file) == database_name


def test_database_name_from_backup_accepts_paths_and_nested_directories():
    module = _module(".backup")

    from_string = module.database_name_from_backup("database.20261019120000.backup")
    from_path = module.database_name_from_backup(
        Path("backups") / "daily" / "database.20261019120000.backup"
    )

    assert from_string == from_path == "database"


def test_database_name_from_backup_falls_back_for_unknown_extensions():
    module = _module(".backup")

    assert (
        module.database_name_from_backup("database.20261019120000.custom") == "database"
    )
    assert (
        module.database_name_from_backup("database.20261019120000.custom.gz")
        == "database"
    )


@pytest.mark.parametrize("file_extension", [".backup", ".backup.gz"])
def test_backup_file_glob_matches_generated_backups(tmp_path, file_extension):
    module = _module(file_extension)

    assert module.backup_file_glob() == f"**/*{file_extension}"
    assert module.backup_file_glob("database") == f"**/database.*{file_extension}"

    nested = tmp_path / "daily" / "2026" / "10" / "19"
    nested.mkdir(parents=True)
    backup_file = nested / module.backup_file_name("database", "20261019120000")
    backup_file.write_bytes(PAYLOAD)

    assert list(tmp_path.glob(module.backup_file_glob())) == [backup_file]
    assert list(tmp_path.glob(module.backup_file_glob("database"))) == [backup_file]
    assert list(tmp_path.glob(module.backup_file_glob("other"))) == []
