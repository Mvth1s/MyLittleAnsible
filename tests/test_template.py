import hashlib
import logging
from unittest.mock import MagicMock

import pytest

from mla.modules import MODULES
from mla.modules.base import ModuleError, ModuleResult
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
    with pytest.raises(ModuleError, match="introuvable"):
        Template({"src": "/nope/nope.j2", "dest": "/x"})._params()


def test_params_vars_defaults_to_empty_dict(tmp_path):
    f = tmp_path / "a.j2"
    f.write_text("x")
    params = Template({"src": str(f), "dest": "/x"})._params()
    assert params == (str(f), "/x", {})


def test_params_vars_must_be_a_dict(tmp_path):
    f = tmp_path / "a.j2"
    f.write_text("x")
    with pytest.raises(ModuleError, match="dictionnaire"):
        Template({"src": str(f), "dest": "/x", "vars": [1, 2]})._params()


# --- _render -----------------------------------------------------------


def test_render_substitutes_variables(tmp_path):
    f = tmp_path / "a.j2"
    f.write_text("listen {{ port }};")

    rendered = Template({})._render(str(f), {"port": 8000})

    assert rendered == "listen 8000;"


def test_render_uses_default_filter_for_missing_var(tmp_path):
    f = tmp_path / "a.j2"
    f.write_text("server_name {{ name | default('localhost') }};")

    rendered = Template({})._render(str(f), {})

    assert rendered == "server_name localhost;"


def test_render_missing_variable_without_default_raises(tmp_path):
    f = tmp_path / "a.j2"
    f.write_text("listen {{ port }};")

    with pytest.raises(ModuleError):
        Template({})._render(str(f), {})


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


def test_process_no_change_skips_sftp(template_file, monkeypatch):
    rendered = "listen 8000;"
    digest = hashlib.sha256(rendered.encode()).hexdigest()
    monkeypatch.setattr("mla.modules.template.run_remote_cmd",
                        lambda cmd, c: cmd_result(f"{digest}  x\n"))
    ssh = MagicMock()

    result = Template({
        "src": str(template_file), "dest": "/dst",
        "vars": {"listen_port": 8000},
    }).process(ssh)

    assert result == ModuleResult(changed=False)
    ssh.open_sftp.assert_not_called()


def test_process_pushes_rendered_content_when_different(
        template_file, monkeypatch):
    calls = []

    def fake_run(cmd, c):
        calls.append(cmd)
        if cmd.startswith("sha256sum"):
            return cmd_result("", exit_code=1)   # fichier distant absent
        return cmd_result()

    monkeypatch.setattr("mla.modules.template.run_remote_cmd", fake_run)
    ssh = MagicMock()

    result = Template({
        "src": str(template_file), "dest": "/etc/nginx/default",
        "vars": {"listen_port": 8000},
    }).process(ssh)

    assert result == ModuleResult(changed=True)
    put_call = ssh.open_sftp.return_value.putfo.call_args
    assert put_call.args[0].getvalue() == b"listen 8000;"
    assert put_call.args[1] == "/etc/nginx/default"
    assert any(c.startswith("mkdir -p") for c in calls)


def test_process_dry_run_does_not_push(template_file, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr("mla.modules.template.run_remote_cmd",
                        lambda cmd, c: cmd_result("", exit_code=1))
    ssh = MagicMock()

    result = Template({
        "src": str(template_file), "dest": "/dst",
        "vars": {"listen_port": 8000},
    }).process(ssh, dry_run=True)

    assert result == ModuleResult(changed=True)
    ssh.open_sftp.assert_not_called()
