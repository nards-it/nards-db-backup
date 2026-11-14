import os
from pathlib import Path

import pytest

from app.modules.abstract_module import AbstractModule
from app.scheduler import Scheduler


class _BackupModule(AbstractModule):
    """In-memory test double for the scheduler's backup lifecycle."""

    def __init__(self, file_extension: str):
        super().__init__(
            "host", "port", "user", "password", "maintenance", file_extension
        )
        self.backup_destinations = []
        self.compressed_files = []

    def list_all_databases(self):
        return ["database"]

    def _backup_database(self, name: str, destination_file: Path) -> bool:
        self.backup_destinations.append(destination_file)
        destination_file.write_bytes(b"backup")
        return True

    def compress_backup(self, backup_file: Path) -> Path:
        self.compressed_files.append(backup_file)
        return super().compress_backup(backup_file)

    def _restore_database(self, name: str, source_file: Path) -> bool:
        return True


@pytest.mark.parametrize(
    ("file_extension", "should_compress"),
    [(".backup", False), (".backup.gz", True)],
)
def test_scheduler_compresses_only_gzip_extensions(
    tmp_path, file_extension, should_compress
):
    module = _BackupModule(file_extension)
    scheduler = Scheduler(module, cron_configs=[], backup_dir=tmp_path)

    scheduler.run_backup("daily", retention_max=1)

    backup_destination = module.backup_destinations[0]
    assert backup_destination.suffix == ".backup"
    assert (module.compressed_files == [backup_destination]) is should_compress

    created_backups = list((tmp_path / "daily").glob(module.backup_file_glob()))
    assert len(created_backups) == 1
    assert created_backups[0].exists()


def test_retention_only_deletes_backups_for_exact_database(tmp_path):
    module = _BackupModule(".sql")
    scheduler = Scheduler(module, cron_configs=[], backup_dir=tmp_path)
    directory = tmp_path / "daily"
    directory.mkdir()
    old = directory / "alpha.20240101000000.sql"
    new = directory / "alpha.20240102000000.sql"
    other = directory / "alpha.billing.20240101000000.sql"
    sidecar = directory / "alpha.20240101000000.pre.sql"
    for file in (old, new, other, sidecar):
        file.write_text("data")
    os.utime(old, (1, 1))
    os.utime(new, (2, 2))

    scheduler.cleanup_old_backups("daily", "alpha", retention_max=1)

    assert not old.exists()
    assert all(file.exists() for file in (new, other, sidecar))
