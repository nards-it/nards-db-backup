from pathlib import Path

import pytest

from app.modules.abstract_module import AbstractModule
from app.scheduler import Scheduler


class _BackupModule(AbstractModule):
    """In-memory test double for the scheduler's backup lifecycle."""

    def __init__(self, file_extension: str):
        super().__init__("host", "port", "user", "password", "maintenance", file_extension)
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
