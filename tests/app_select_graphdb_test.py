import os
import sys


def _import_app_py(module_name: str, rootdir) -> object:
    """Import app.py fresh under a unique module name."""
    import importlib.util

    sys.modules.pop("app.config", None)

    path = os.path.join(str(rootdir), "app.py")
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_app_import_selects_graphdb_module(monkeypatch, pytestconfig):
    from app.modules.graphdb_module import GraphDBModule

    # Set env to select GraphDB in app.py
    monkeypatch.setenv("DB_TYPE", "graphdb")
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_PORT", "7200")
    # GraphDB Free often runs without auth; leave empty
    monkeypatch.setenv("DB_USER", "")
    monkeypatch.setenv("DB_PASSWORD", "")
    # Not used by GraphDBModule; kept for compatibility
    monkeypatch.setenv("DB_MAINTENANCE_NAME", "")

    app_mod = _import_app_py("app_main_graphdb", pytestconfig.rootdir)

    assert isinstance(app_mod.db_module, GraphDBModule)
