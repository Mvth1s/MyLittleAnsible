import hashlib
import logging
from unittest.mock import MagicMock

import pytest

from mla.modules import MODULES
from mla.modules.base import ModuleError, ModuleResult, sudo_cmd
from mla.modules.template import Template
from mla.ssh import CmdResult


def cmd_result(stdout="", exit_code=0):
    return CmdResult(stdout=stdout, stderr="", exit_code=exit_code)


def test_registry_exposes_template():
    assert MODULES["template"] is Template


# --- _params ---------------------------------------------------------------


def test_params_missing_src():
    with pytest.raises(ModuleError, match="src"):
        Template({"dest": "/x"})._params()


def test_params_missing_dest(tmp_path):
    f = tmp_path / "a.j2"
    f.write_text("x")
    with pytest.raises(ModuleError, match="dest"):
        Template({"src": str(f)})._params()


def test_params_src_not_found():
    with pytest.raises(ModuleError, match="not found"):
        Template({"src": "/nope/nope.j2", "dest": "/x"})._params()


def test_params_vars_defaults_to_empty_dict(tmp_path):
    f = tmp_path / "a.j2"
    f.write_text("x")
    params = Template({"src": str(f), "dest": "/x"})._params()
    assert params == (str(f), "/x", {})


def test_params_vars_must_be_a_dict(tmp_path):
    f = tmp_path / "a.j2"
    f.write_text("x")
    with pytest.raises(ModuleError, match="dict"):
        Template({"src": str(f), "dest": "/x", "vars": [1, 2]})._params()


# --- _render -----------------------------------------------------------


def test_render_substitutes_variables(tmp_path):
    f = tmp_path / "a.j2"
    f.write_text("listen {{ port }};")

    rendered = Template({})._render(str(f), {"port": 8000})

    assert rendered == "listen 8000;"


def test_render_uses_default_filter_for_missing_var(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    f = tmp_path / "a.j2"
    f.write_text("server_name {{ name | default('localhost') }};")

    rendered = Template({})._render(str(f), {})

    assert rendered == "server_name localhost;"
    assert caplog.records == []


def test_render_missing_variable_renders_empty_and_warns(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    f = tmp_path / "a.j2"
    f.write_text("listen {{ port }};")

    rendered = Template({})._render(str(f), {})

    assert rendered == "listen ;"
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "port" in warnings[0].getMessage()


def test_render_keeps_trailing_newline(tmp_path):
    f = tmp_path / "a.j2"
    f.write_text("server {\n    listen {{ port }};\n}\n")

    rendered = Template({})._render(str(f), {"port": 8000})

    assert rendered == "server {\n    listen 8000;\n}\n"


def test_render_syntax_error_raises(tmp_path):
    f = tmp_path / "a.j2"
    f.write_text("{% if %}")

    with pytest.raises(ModuleError):
        Template({})._render(str(f), {})


# --- _remote_matches -----------------------------------------------------


def test_remote_matches_true(monkeypatch):
    monkeypatch.setattr("mla.modules.template.run_remote_cmd",
                        lambda cmd, c: cmd_result("abc123  /remote\n"))

    assert Template({})._remote_matches(
        object(), "/remote", "abc123") is True


def test_remote_matches_false_on_different_hash(monkeypatch):
    monkeypatch.setattr("mla.modules.template.run_remote_cmd",
                        lambda cmd, c: cmd_result("0" * 64 + "  /remote\n"))

    assert Template({})._remote_matches(
        object(), "/remote", "abc123") is False


def test_remote_matches_false_when_remote_missing(monkeypatch):
    monkeypatch.setattr("mla.modules.template.run_remote_cmd",
                        lambda cmd, c: cmd_result("", exit_code=1))

    assert Template({})._remote_matches(
        object(), "/remote", "abc123") is False


# --- process -------------------------------------------------------------


@pytest.fixture
def template_file(tmp_path):
    f = tmp_path / "default.conf.j2"
    f.write_text("listen {{ listen_port }};")
    return f


def make_ssh():
    ssh = MagicMock()
    sftp = ssh.open_sftp.return_value
    sftp.__enter__.return_value = sftp
    return ssh, sftp


def patch_run(monkeypatch, remote_hash=None):
    calls = []

    def fake_run(cmd, c):
        calls.append(cmd)
        if cmd.startswith("sha256sum"):
            if remote_hash is None:
                return cmd_result("", exit_code=1)   # fichier distant absent
            return cmd_result(f"{remote_hash}  x\n")
        if cmd == "mktemp -d":
            return cmd_result("/tmp/tmp.mla42\n")
        return cmd_result()

    monkeypatch.setattr("mla.modules.template.run_remote_cmd", fake_run)
    monkeypatch.setattr("mla.modules.base.run_remote_cmd", fake_run)
    return calls


PARAMS = {"dest": "/etc/nginx/default", "vars": {"listen_port": 8000}}


def test_process_no_change_skips_sftp(template_file, monkeypatch):
    digest = hashlib.sha256(b"listen 8000;").hexdigest()
    patch_run(monkeypatch, remote_hash=digest)
    ssh, _ = make_ssh()

    result = Template({"src": str(template_file), **PARAMS}).process(ssh)

    assert result == ModuleResult(changed=False)
    ssh.open_sftp.assert_not_called()


def test_process_without_sudo_pushes_rendered_content(template_file,
                                                      monkeypatch):
    calls = patch_run(monkeypatch)
    ssh, sftp = make_ssh()

    result = Template({"src": str(template_file), **PARAMS}).process(ssh)

    assert result == ModuleResult(changed=True)
    put_call = sftp.putfo.call_args
    assert put_call.args[0].getvalue() == b"listen 8000;"
    assert put_call.args[1] == "/etc/nginx/default"
    assert "mkdir -p /etc/nginx" in calls


def test_process_with_sudo_stages_and_installs(template_file, monkeypatch):
    template_file.chmod(0o644)
    calls = patch_run(monkeypatch)
    ssh, sftp = make_ssh()

    Template({"src": str(template_file), **PARAMS}).process(
        ssh, sudo_password="s3cret")

    assert sftp.putfo.call_args.args[1] == "/tmp/tmp.mla42/0"
    install = sudo_cmd(
        "install -D -m 0644 /tmp/tmp.mla42/0 /etc/nginx/default", "s3cret")
    assert calls[-3:] == ["mktemp -d", install, "rm -rf /tmp/tmp.mla42"]


def test_process_dry_run_does_not_push(template_file, monkeypatch):
    template_file.chmod(0o644)
    patch_run(monkeypatch)
    ssh, _ = make_ssh()

    result = Template({"src": str(template_file), **PARAMS}).process(
        ssh, dry_run=True, sudo_password="s3cret")

    assert result == ModuleResult(changed=True, commands=[
        f"install -D -m 0644 {template_file} /etc/nginx/default"])
    ssh.open_sftp.assert_not_called()
