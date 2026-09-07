import logging

import pytest

from mla.modules import MODULES
from mla.modules.base import ModuleError, ModuleResult
from mla.modules.command import Command
from mla.ssh import CmdResult


def test_registry_exposes_command():
    assert MODULES["command"] is Command


def test_build_command_default_shell():
    mod = Command({"command": "echo hello"})

    assert mod._build_command() == "/bin/bash -c 'echo hello'"


def test_build_command_custom_shell():
    mod = Command({"command": "echo hello", "shell": "/bin/sh"})

    assert mod._build_command() == "/bin/sh -c 'echo hello'"


def test_build_command_quotes_dangerous_input():
    mod = Command({"command": "rm -rf / ; echo 'oops'"})

    built = mod._build_command()

    # tout est passé en un seul argument quoté à -c
    assert built.startswith("/bin/bash -c ")
    assert "rm -rf / ; echo" in built


def test_build_command_missing_command_raises():
    mod = Command({})

    with pytest.raises(ModuleError, match="command"):
        mod._build_command()


def test_build_command_empty_command_raises():
    mod = Command({"command": ""})

    with pytest.raises(ModuleError):
        mod._build_command()


def test_process_success_returns_changed(monkeypatch):
    calls = []

    def fake_run(cmd, ssh_client):
        calls.append(cmd)
        return CmdResult(stdout="ok", stderr="", exit_code=0)

    monkeypatch.setattr("mla.modules.command.run_remote_cmd", fake_run)
    mod = Command({"command": "true"})

    result = mod.process(ssh_client=object())

    assert result == ModuleResult(changed=True)
    assert calls == ["/bin/bash -c true"]


def test_process_non_zero_exit_raises_module_error(monkeypatch):
    def fake_run(cmd, ssh_client):
        return CmdResult(stdout="", stderr="boom", exit_code=1)

    monkeypatch.setattr("mla.modules.command.run_remote_cmd", fake_run)
    mod = Command({"command": "false"})

    with pytest.raises(ModuleError, match="boom"):
        mod.process(ssh_client=object())


def test_process_error_falls_back_to_stdout(monkeypatch):
    def fake_run(cmd, ssh_client):
        return CmdResult(stdout="details", stderr="", exit_code=2)

    monkeypatch.setattr("mla.modules.command.run_remote_cmd", fake_run)
    mod = Command({"command": "x"})

    with pytest.raises(ModuleError, match="details"):
        mod.process(ssh_client=object())


def test_process_error_without_output_mentions_exit_code(monkeypatch):
    def fake_run(cmd, ssh_client):
        return CmdResult(stdout="", stderr="", exit_code=5)

    monkeypatch.setattr("mla.modules.command.run_remote_cmd", fake_run)
    mod = Command({"command": "x"})

    with pytest.raises(ModuleError, match="5"):
        mod.process(ssh_client=object())


def test_dry_run_does_not_execute(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    called = []
    monkeypatch.setattr("mla.modules.command.run_remote_cmd",
                        lambda cmd, ssh_client: called.append(cmd))
    mod = Command({"command": "echo hello"})

    result = mod.process(ssh_client=object(), dry_run=True)

    assert result == ModuleResult(changed=False)
    assert called == []
    assert "/bin/bash -c 'echo hello'" in caplog.text
