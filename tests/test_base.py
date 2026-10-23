import pytest

from mla.modules.base import (
    BaseModule,
    ModuleError,
    ModuleResult,
    run_checked,
    run_sudo,
    sudo_cmd,
)
from mla.ssh import CmdResult


def test_init_stores_params():
    m = BaseModule({"name": "nginx"})
    assert m.params == {"name": "nginx"}


def test_process_not_implemented():
    m = BaseModule({})
    with pytest.raises(NotImplementedError):
        m.process(ssh_client=None)


def test_subclass_can_override_process():
    class DummyModule(BaseModule):
        name = "dummy"

        def process(self, ssh_client):
            return ModuleResult(changed=True)

    result = DummyModule({}).process(ssh_client=None)
    assert result.changed is True


# --- sudo_cmd ---------------------------------------------------------------


def test_sudo_cmd_format():
    assert sudo_cmd("systemctl start nginx") == (
        "sudo -S -p '' sh -c 'systemctl start nginx'")


def test_sudo_cmd_quotes_command():
    cmd = sudo_cmd("echo a > /etc/x && echo b")

    assert cmd == "sudo -S -p '' sh -c 'echo a > /etc/x && echo b'"


# --- run_sudo ---------------------------------------------------------------


def test_run_sudo_sends_password_on_stdin_only(monkeypatch):
    seen = []

    def fake_run(cmd, c, stdin_data=None):
        seen.append((cmd, stdin_data))
        return CmdResult("", "", 0)

    monkeypatch.setattr("mla.modules.base.run_remote_cmd", fake_run)

    run_sudo("apt-get install -y x", object(), "p a'ss$", "apt")

    assert seen == [(sudo_cmd("apt-get install -y x"), "p a'ss$\n")]
    assert "p a" not in seen[0][0]


def test_run_sudo_raises_on_failure(monkeypatch):
    monkeypatch.setattr("mla.modules.base.run_remote_cmd",
                        lambda cmd, c, stdin_data=None:
                        CmdResult("", "Sorry, try again.\n", 1))

    with pytest.raises(ModuleError, match="Sorry"):
        run_sudo("true", object(), "bad", "true")


# --- run_checked ------------------------------------------------------------


def test_run_checked_returns_result(monkeypatch):
    monkeypatch.setattr("mla.modules.base.run_remote_cmd",
                        lambda cmd, c, stdin_data=None:
                        CmdResult("out", "", 0))

    assert run_checked("true", object(), "true").stdout == "out"


def test_run_checked_raises_with_stderr(monkeypatch):
    monkeypatch.setattr("mla.modules.base.run_remote_cmd",
                        lambda cmd, c, stdin_data=None:
                        CmdResult("", "denied\n", 1))

    with pytest.raises(ModuleError, match="^denied$"):
        run_checked("false", object(), "false")


def test_run_checked_raises_with_code_without_output(monkeypatch):
    monkeypatch.setattr("mla.modules.base.run_remote_cmd",
                        lambda cmd, c, stdin_data=None:
                        CmdResult("", "", 7))

    with pytest.raises(ModuleError, match="mkdir failed .exit code 7."):
        run_checked("mkdir x", object(), "mkdir")
