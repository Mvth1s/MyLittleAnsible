import pytest

from mla.modules.base import (
    BaseModule,
    ModuleError,
    ModuleResult,
    run_checked,
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
    assert sudo_cmd("systemctl start nginx", "s3cret") == (
        "printf '%s\\n' s3cret | sudo -S -p '' sh -c 'systemctl start nginx'")


def test_sudo_cmd_quotes_password_and_command():
    cmd = sudo_cmd("echo a > /etc/x && echo b", "p a'ss")

    assert cmd.startswith("printf '%s\\n' 'p a'\"'\"'ss' | ")
    assert cmd.endswith("sh -c 'echo a > /etc/x && echo b'")
    assert cmd.count("sudo") == 1


# --- run_checked ------------------------------------------------------------


def test_run_checked_returns_result(monkeypatch):
    monkeypatch.setattr("mla.modules.base.run_remote_cmd",
                        lambda cmd, c: CmdResult("out", "", 0))

    assert run_checked("true", object(), "true").stdout == "out"


def test_run_checked_raises_with_stderr(monkeypatch):
    monkeypatch.setattr("mla.modules.base.run_remote_cmd",
                        lambda cmd, c: CmdResult("", "denied\n", 1))

    with pytest.raises(ModuleError, match="^denied$"):
        run_checked("false", object(), "false")


def test_run_checked_raises_with_code_without_output(monkeypatch):
    monkeypatch.setattr("mla.modules.base.run_remote_cmd",
                        lambda cmd, c: CmdResult("", "", 7))

    with pytest.raises(ModuleError, match="mkdir failed .exit code 7."):
        run_checked("mkdir x", object(), "mkdir")
