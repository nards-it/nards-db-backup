from pathlib import Path
from unittest.mock import patch

from app.modules.postgis_module import PostGISModule


def test_compressed_restore_passes_original_backup_path_to_postgis(tmp_path):
    module = PostGISModule("host", "5432", "user", "password", "postgres")
    archive = tmp_path / "database.20261019120000.backup.gz"
    temporary = Path("/tmp/private/database.20261019120000.backup")

    with patch.object(module, "_restore_database", return_value=True) as restore:
        assert module._restore_prepared_database("database", temporary, archive)

    restore.assert_called_once_with("database", temporary, archive.with_suffix(""))
