import os
import sys
from pathlib import Path

import pytest
from flask.cli import ScriptInfo

from app.modules.abstract_module import AbstractModule


def _import_app_py(module_name: str, rootdir) -> object:
    """Import app.py fresh under a unique module name."""
    import importlib.util

    # Ensure Config is re-evaluated with the current environment
    sys.modules.pop("app.config", None)

    path = os.path.join(str(rootdir), "app.py")
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _RestoreModule(AbstractModule):
    """AbstractModule double recording the restore calls made by the CLI."""

    def __init__(self, file_extension: str = ".backup"):
        super().__init__(
            "host", "port", "user", "password", "maintenance", file_extension
        )
        self.restore_calls = []
        self.restore_result = True

    def list_all_databases(self):
        return []

    def _backup_database(self, name: str, destination_file: Path) -> bool:
        return True

    def _restore_database(self, name: str, source_file: Path) -> bool:
        self.restore_calls.append((name, Path(source_file)))
        return self.restore_result


@pytest.fixture
def cli_app(monkeypatch, tmp_path, pytestconfig):
    """Import app.py with a fake database module and a temporary backup dir."""
    monkeypatch.setenv("DB_TYPE", "mysql")
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_PORT", "3306")
    monkeypatch.setenv("DB_USER", "user")
    monkeypatch.setenv("DB_PASSWORD", "password")
    monkeypatch.setenv("DB_MAINTENANCE_NAME", "mysql")

    app_mod = _import_app_py(f"app_cli_restore_{tmp_path.name}", pytestconfig.rootdir)
    app_mod.db_module = _RestoreModule()
    app_mod.Config.BACKUP_DIR = tmp_path
    app_mod.Config.RESTORE_CONFIG_NAME = ""
    return app_mod, app_mod.db_module


def _invoke_restore(app_mod, name_or_path: str) -> int:
    """Run the ``flask restore`` command and return its exit code.

    ``click.testing.CliRunner`` is deliberately not used: with ``log_cli = true``
    (see ``pytest.ini``) pytest's live-logging handler suspends the global
    capture while the command logs, which closes the stream CliRunner installs
    as ``sys.stdout`` and makes ``invoke`` fail with ``ValueError: I/O operation
    on closed file``. Going through the application CLI group with an explicit
    ``ScriptInfo`` (the same object CliRunner would provide) runs the very same
    code path and returns the same exit codes as ``flask restore``, without any
    stdout capture.
    """
    script_info = ScriptInfo(create_app=lambda: app_mod.app)
    with pytest.raises(SystemExit) as exit_info:
        app_mod.app.cli.main(
            args=["restore", name_or_path],
            prog_name="flask",
            obj=script_info,
            standalone_mode=True,
        )
    exit_code = exit_info.value.code
    if exit_code is None:
        return 0
    return int(exit_code)


def _make_backup_file(tmp_path: Path, relative_path: str, content: bytes) -> Path:
    backup_file = tmp_path / relative_path
    backup_file.parent.mkdir(parents=True, exist_ok=True)
    backup_file.write_bytes(content)
    return backup_file


def test_restore_from_file_path_succeeds(cli_app, tmp_path):
    app_mod, db_module = cli_app
    backup_file = _make_backup_file(
        tmp_path, "mydb.20240101000000.backup", b"dummy backup"
    )

    exit_code = _invoke_restore(app_mod, str(backup_file))

    assert exit_code == 0
    assert db_module.restore_calls == [("mydb", backup_file)]


def test_restore_from_file_path_fails_with_non_zero_exit_code(
    cli_app, tmp_path, capsys
):
    app_mod, db_module = cli_app
    db_module.restore_result = False
    backup_file = _make_backup_file(
        tmp_path, "mydb.20240101000000.backup", b"dummy backup"
    )

    exit_code = _invoke_restore(app_mod, str(backup_file))

    assert exit_code == 1
    assert "Error: Restore failed" in capsys.readouterr().err
    assert db_module.restore_calls == [("mydb", backup_file)]


def test_restore_from_config_name_uses_the_latest_backup(cli_app, tmp_path):
    app_mod, db_module = cli_app
    older = _make_backup_file(
        tmp_path, "hourly/2024/1/1/mydb.20240101000000.backup", b"older"
    )
    newer = _make_backup_file(
        tmp_path, "hourly/2024/1/1/mydb.20240102000000.backup", b"newer"
    )
    os.utime(older, (1_000_000, 1_000_000))
    os.utime(newer, (2_000_000, 2_000_000))

    exit_code = _invoke_restore(app_mod, "hourly")

    assert exit_code == 0
    assert db_module.restore_calls == [("mydb", newer)]


def test_restore_from_config_ignores_recovery_snapshot(cli_app, tmp_path):
    app_mod, _ = cli_app
    db_module = _RestoreModule(".nq")
    app_mod.db_module = db_module
    backup = _make_backup_file(tmp_path, "daily/mydb.20240101000000.nq", b"backup")
    snapshot = _make_backup_file(
        tmp_path, "daily/.graphdb-recovery-test/previous.20240102000000.nq", b"old"
    )
    os.utime(backup, (1, 1))
    os.utime(snapshot, (2, 2))

    assert _invoke_restore(app_mod, "daily") == 0
    assert db_module.restore_calls == [("mydb", backup)]


def test_restore_from_config_ignores_newer_postgis_script(cli_app, tmp_path):
    app_mod, _ = cli_app
    db_module = _RestoreModule(".sql")
    app_mod.db_module = db_module
    backup = _make_backup_file(tmp_path, "daily/mydb.20240101000000.sql", b"backup")
    script = _make_backup_file(tmp_path, "daily/mydb.20240101000000.pre.sql", b"script")
    os.utime(backup, (1, 1))
    os.utime(script, (2, 2))

    assert _invoke_restore(app_mod, "daily") == 0
    assert db_module.restore_calls == [("mydb", backup)]


def test_restore_from_explicit_nonstandard_file_remains_supported(cli_app, tmp_path):
    app_mod, db_module = cli_app
    backup = _make_backup_file(tmp_path, "manual.backup", b"backup")

    assert _invoke_restore(app_mod, str(backup)) == 0
    assert db_module.restore_calls == [("manual", backup)]


def test_restore_from_config_name_without_backups_fails(cli_app, capsys):
    app_mod, db_module = cli_app

    exit_code = _invoke_restore(app_mod, "hourly")

    assert exit_code == 1
    assert "Error: No backups found for configuration 'hourly'" in (
        capsys.readouterr().err
    )
    assert db_module.restore_calls == []


def test_restore_from_config_name_failure_exits_non_zero(cli_app, tmp_path, capsys):
    app_mod, db_module = cli_app
    db_module.restore_result = False
    backup_file = _make_backup_file(
        tmp_path, "daily/2024/1/1/mydb.20240101000000.backup", b"dummy"
    )

    exit_code = _invoke_restore(app_mod, "daily")

    assert exit_code == 1
    assert "Error: Restore failed" in capsys.readouterr().err
    assert db_module.restore_calls == [("mydb", backup_file)]
