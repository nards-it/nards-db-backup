import os
import sys


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


def test_app_import_selects_mongodb_module(monkeypatch, pytestconfig):
    from app.modules.mongodb_module import MongoDBModule

    # Set env to select MongoDB in app.py
    monkeypatch.setenv("DB_TYPE", "mongodb")
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_PORT", "27017")
    monkeypatch.setenv("DB_USER", "user")
    monkeypatch.setenv("DB_PASSWORD", "password")
    # Maintenance DB commonly 'admin' for MongoDB
    monkeypatch.setenv("DB_MAINTENANCE_NAME", "admin")

    app_mod = _import_app_py("app_main_mongodb", pytestconfig.rootdir)

    assert isinstance(app_mod.db_module, MongoDBModule)
