import logging
import subprocess

import pytest

from app.modules.mysql_module import MySQLModule


@pytest.mark.parametrize("operation", ["backup", "recreate", "import"])
def test_mysql_command_failures_do_not_log_password(
    monkeypatch, caplog, tmp_path, operation
):
    password = "secret\\password-for-test"
    module = MySQLModule("host", "3306", "user", password, "maintenance")
    calls = 0

    def run(command, **kwargs):
        nonlocal calls
        calls += 1
        if operation != "import" or calls == 2:
            assert kwargs["stderr"] == subprocess.PIPE
            raise subprocess.CalledProcessError(
                1,
                command,
                stderr=f"Access denied for {password}; escaped {password!r}",
            )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", run)
    with caplog.at_level(logging.ERROR):
        if operation == "backup":
            result = module.backup_database("database", tmp_path / "database.backup")
        else:
            result = module.restore_database("database", tmp_path / "database.backup")

    assert result is False
    assert password not in caplog.text
    assert repr(password)[1:-1] not in caplog.text
    assert "status 1" in caplog.text
    assert "Access denied" in caplog.text
    assert "[REDACTED]" in caplog.text
    if operation != "backup":
        assert (
            "database recreation" if operation == "recreate" else "import"
        ) in caplog.text


def test_mysql_unexpected_restore_error_logs_redacted_exception_text(
    monkeypatch, caplog, tmp_path
):
    password = "secret-password-for-test"
    module = MySQLModule("host", "3306", "user", password, "maintenance")

    def fail(*args, **kwargs):
        raise RuntimeError(f"command contained {password}")

    monkeypatch.setattr(subprocess, "run", fail)
    with caplog.at_level(logging.ERROR):
        assert not module.restore_database("database", tmp_path / "database.backup")

    assert password not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "command contained [REDACTED]" in caplog.text


def test_mysql_successful_command_logs_redacted_warning(monkeypatch, caplog, tmp_path):
    password = "secret-password-for-test"
    module = MySQLModule("host", "3306", "user", password, "maintenance")

    def run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stderr=f"Warning: {password}")

    monkeypatch.setattr(subprocess, "run", run)
    with caplog.at_level(logging.WARNING):
        assert module.backup_database("database", tmp_path / "database.backup")

    assert "Warning: [REDACTED]" in caplog.text
    assert password not in caplog.text
