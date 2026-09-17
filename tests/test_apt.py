import logging

import pytest

from mla.modules import MODULES
from mla.modules.apt import Apt
from mla.modules.base import ModuleError, ModuleResult
from mla.ssh import CmdResult

PASSWORD = "s3cret"
INSTALL = (
    "printf '%s\\n' s3cret | "
    "sudo -S env DEBIAN_FRONTEND=noninteractive apt-get install -y nginx"
)
REMOVE = (
    "printf '%s\\n' s3cret | "
    "sudo -S env DEBIAN_FRONTEND=noninteractive apt-get remove -y nginx"
)


def make_run(installed, action_exit=0, action_stderr="", action_stdout=""):
    """
    Faux run_remote_cmd : répond selon la commande reçue.
    - 'dpkg-query ...'  -> exit 0 si `installed`, 1 sinon
    - le reste (apt-get) -> CmdResult(action_stdout/stderr/exit)
    Retourne (fake_run, calls) où `calls` accumule les commandes vues.
    """
    calls = []

    def fake_run(cmd, ssh_client):
        calls.append(cmd)
        if "dpkg-query" in cmd:
            return CmdResult("", "", 0 if installed else 1)
        return CmdResult(action_stdout, action_stderr, action_exit)

    return fake_run, calls


def test_registry_exposes_apt():
    assert MODULES["apt"] is Apt


def test_params_missing_name_raises():
    with pytest.raises(ModuleError, match="name"):
        Apt({})._params()


def test_params_invalid_state_raises():
    with pytest.raises(ModuleError, match="state"):
        Apt({"name": "nginx", "state": "instaled"})._params()


def test_params_default_state_is_present():
    assert Apt({"name": "nginx"})._params() == ("nginx", "present")


def test_present_already_installed_is_ok(monkeypatch):
    fake_run, calls = make_run(installed=True)
    monkeypatch.setattr("mla.modules.apt.run_remote_cmd", fake_run)

    result = Apt({"name": "nginx"}).process(ssh_client=object())

    assert result == ModuleResult(changed=False)
    assert not any("apt-get" in c for c in calls)


def test_present_not_installed_installs(monkeypatch):
    fake_run, calls = make_run(installed=False)
    monkeypatch.setattr("mla.modules.apt.run_remote_cmd", fake_run)

    result = Apt({"name": "nginx"}).process(
        ssh_client=object(), sudo_password=PASSWORD)

    assert result == ModuleResult(changed=True)
    assert calls[-1] == INSTALL


def test_absent_installed_removes(monkeypatch):
    fake_run, calls = make_run(installed=True)
    monkeypatch.setattr("mla.modules.apt.run_remote_cmd", fake_run)

    result = Apt({"name": "nginx", "state": "absent"}).process(
        ssh_client=object(), sudo_password=PASSWORD)

    assert result == ModuleResult(changed=True)
    assert calls[-1] == REMOVE


def test_absent_not_installed_is_ok(monkeypatch):
    fake_run, calls = make_run(installed=False)
    monkeypatch.setattr("mla.modules.apt.run_remote_cmd", fake_run)

    result = Apt({"name": "nginx", "state": "absent"}).process(
        ssh_client=object())

    assert result == ModuleResult(changed=False)
    assert not any("apt-get" in c for c in calls)


def test_action_failure_raises_module_error(monkeypatch):
    fake_run, _ = make_run(installed=False, action_exit=100,
                           action_stderr="E: unable to locate package")
    monkeypatch.setattr("mla.modules.apt.run_remote_cmd", fake_run)

    with pytest.raises(ModuleError, match="unable to locate"):
        Apt({"name": "nginx"}).process(
            ssh_client=object(), sudo_password=PASSWORD)


def test_action_failure_without_output_mentions_code(monkeypatch):
    fake_run, _ = make_run(installed=False, action_exit=100)
    monkeypatch.setattr("mla.modules.apt.run_remote_cmd", fake_run)

    with pytest.raises(ModuleError, match="100"):
        Apt({"name": "nginx"}).process(
            ssh_client=object(), sudo_password=PASSWORD)


def test_missing_sudo_password_raises_when_change_needed(monkeypatch):
    fake_run, _ = make_run(installed=False)
    monkeypatch.setattr("mla.modules.apt.run_remote_cmd", fake_run)

    with pytest.raises(ModuleError, match="mot de passe"):
        Apt({"name": "nginx"}).process(ssh_client=object())


def test_dry_run_does_not_execute_action(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    fake_run, calls = make_run(installed=False)
    monkeypatch.setattr("mla.modules.apt.run_remote_cmd", fake_run)

    result = Apt({"name": "nginx"}).process(ssh_client=object(), dry_run=True)

    assert result == ModuleResult(changed=True)
    assert not any("apt-get" in c for c in calls)
    assert "apt-get install -y nginx" in caplog.text
