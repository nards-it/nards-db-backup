import os
import sys
from pathlib import Path


def _import_app_py(module_name: str, rootdir) -> object:
    """Import app.py fresh under a unique module name."""
    import importlib.util

    # Ensure Config is re-evaluated with current env
    sys.modules.pop("app.config", None)

    path = os.path.join(str(rootdir), "app.py")
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FakeDB:
    def __init__(self, calls):
        self.calls = calls
        self.restore_called = False
        self.restore_args = None

    def restore_database(self, name, source_file):
        self.calls.append("restore")
        self.restore_called = True
        self.restore_args = (name, Path(source_file))
        return True


class _FakeScheduler:
    def __init__(self, calls):
        self.calls = calls
        self.start_called = False

    def start(self):
        self.calls.append("start")
        self.start_called = True


def test_run_app_with_startup_restore(monkeypatch, tmp_path, pytestconfig):
    # Fresh import of app.py
    app_mod = _import_app_py("app_main_module", pytestconfig.rootdir)

    # Prepare fake scheduler and db module
    calls = []
    fake_db = _FakeDB(calls)
    fake_sched = _FakeScheduler(calls)

    # Replace module-level instances
    app_mod.db_module = fake_db
    app_mod.scheduler = fake_sched

    # Point BACKUP_DIR to temp dir and create a fake backup
    cron_name = "hourly"
    backup_dir = tmp_path / cron_name / "2024" / "1" / "1"
    backup_dir.mkdir(parents=True)
    backup_file = backup_dir / "mydb.20240101000000.backup"
    backup_file.write_text("dummy")

    # Ensure Config reads our temp dirs and that restore is enabled
    app_mod.Config.BACKUP_DIR = tmp_path
    app_mod.Config.RESTORE_CONFIG_NAME = cron_name

    # Run without starting the Flask server
    app_mod.run_app(start_server=False)

    # Assert order: restore first, then scheduler start
    assert calls == ["restore", "start"]

    # Assert restore called with expected params
    assert fake_db.restore_called is True
    assert fake_db.restore_args is not None
    name, src = fake_db.restore_args
    assert name == "mydb"
    assert src == backup_file


def test_run_app_without_startup_restore(monkeypatch, tmp_path, pytestconfig):
    app_mod = _import_app_py("app_main_module_no_restore", pytestconfig.rootdir)

    calls = []
    fake_db = _FakeDB(calls)
    fake_sched = _FakeScheduler(calls)

    app_mod.db_module = fake_db
    app_mod.scheduler = fake_sched

    # No restore configured
    app_mod.Config.BACKUP_DIR = tmp_path
    app_mod.Config.RESTORE_CONFIG_NAME = ""

    app_mod.run_app(start_server=False)

    # Only scheduler should start
    assert calls == ["start"]
    assert fake_db.restore_called is False
