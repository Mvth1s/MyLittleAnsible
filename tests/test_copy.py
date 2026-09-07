import hashlib
import logging
from unittest.mock import MagicMock

import pytest

from mla.modules import MODULES
from mla.modules.base import ModuleError, ModuleResult
from mla.modules.copy import Copy
from mla.ssh import CmdResult


def cmd_result(stdout="", exit_code=0):
    return CmdResult(stdout=stdout, stderr="", exit_code=exit_code)


def test_registry_exposes_copy():
    assert MODULES["copy"] is Copy


# --- _params ---------------------------------------------------------------


def test_params_missing_src():
    with pytest.raises(ModuleError, match="src"):
        Copy({"dest": "/x"})._params()


def test_params_missing_dest(tmp_path):
    f = tmp_path / "a"
    f.write_text("x")
    with pytest.raises(ModuleError, match="dest"):
        Copy({"src": str(f)})._params()


def test_params_src_not_found():
    with pytest.raises(ModuleError, match="introuvable"):
        Copy({"src": "/nope/nope", "dest": "/x"})._params()


def test_params_backup_defaults_to_false(tmp_path):
    f = tmp_path / "a"
    f.write_text("x")
    params = Copy({"src": str(f), "dest": "/x"})._params()
    assert params == (str(f), "/x", False)


# --- _targets ------------------------------------------------------------


def test_targets_single_file(tmp_path):
    f = tmp_path / "conf"
    f.write_text("x")
    assert Copy({})._targets(str(f), "/etc/conf") == [(str(f), "/etc/conf")]


def test_targets_directory_keeps_tree(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "sub" / "b.txt").write_text("b")

    pairs = sorted(Copy({})._targets(str(tmp_path), "/dst"))

    assert pairs == [
        (str(tmp_path / "a.txt"), "/dst/a.txt"),
        (str(tmp_path / "sub" / "b.txt"), "/dst/sub/b.txt"),
    ]


# --- _sha256_local ------------------------------------------------------


def test_sha256_local(tmp_path):
    f = tmp_path / "a"
    f.write_bytes(b"hello")
    assert Copy._sha256_local(str(f)) == hashlib.sha256(b"hello").hexdigest()


# --- _remote_matches --------------------------------------------------


def test_remote_matches_true(tmp_path, monkeypatch):
    f = tmp_path / "a"
    f.write_bytes(b"data")
    digest = Copy._sha256_local(str(f))
    monkeypatch.setattr("mla.modules.copy.run_remote_cmd",
                        lambda cmd, c: cmd_result(f"{digest}  /remote\n"))

    assert Copy({})._remote_matches(object(), str(f), "/remote") is True


def test_remote_matches_false_on_different_hash(tmp_path, monkeypatch):
    f = tmp_path / "a"
    f.write_bytes(b"data")
    monkeypatch.setattr("mla.modules.copy.run_remote_cmd",
                        lambda cmd, c: cmd_result("0" * 64 + "  /remote\n"))

    assert Copy({})._remote_matches(object(), str(f), "/remote") is False


def test_remote_matches_false_when_remote_missing(tmp_path, monkeypatch):
    f = tmp_path / "a"
    f.write_bytes(b"data")
    monkeypatch.setattr("mla.modules.copy.run_remote_cmd",
                        lambda cmd, c: cmd_result("", exit_code=1))

    assert Copy({})._remote_matches(object(), str(f), "/remote") is False


# --- process -----------------------------------------------------------


@pytest.fixture
def one_file(tmp_path):
    f = tmp_path / "index.html"
    f.write_text("hello")
    return f


def test_process_no_change_skips_sftp(one_file, monkeypatch):
    digest = Copy._sha256_local(str(one_file))
    monkeypatch.setattr("mla.modules.copy.run_remote_cmd",
                        lambda cmd, c: cmd_result(f"{digest}  x\n"))
    ssh = MagicMock()

    result = Copy({"src": str(one_file), "dest": "/dst"}).process(ssh)

    assert result == ModuleResult(changed=False)
    ssh.open_sftp.assert_not_called()


def test_process_copies_when_different(one_file, monkeypatch):
    calls = []

    def fake_run(cmd, c):
        calls.append(cmd)
        if cmd.startswith("sha256sum"):
            return cmd_result("", exit_code=1)   # fichier distant absent
        return cmd_result()

    monkeypatch.setattr("mla.modules.copy.run_remote_cmd", fake_run)
    ssh = MagicMock()

    result = Copy(
        {"src": str(one_file), "dest": "/dst/index.html"}
    ).process(ssh)

    assert result == ModuleResult(changed=True)
    ssh.open_sftp.return_value.put.assert_called_once_with(
        str(one_file), "/dst/index.html")
    assert any(c.startswith("mkdir -p") for c in calls)


def test_process_dry_run_does_not_copy(one_file, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr("mla.modules.copy.run_remote_cmd",
                        lambda cmd, c: cmd_result("", exit_code=1))
    ssh = MagicMock()

    result = Copy({"src": str(one_file), "dest": "/dst"}).process(
        ssh, dry_run=True)

    assert result == ModuleResult(changed=True)
    ssh.open_sftp.assert_not_called()


def test_process_backup_issues_cp(one_file, monkeypatch):
    cmds = []

    def fake_run(cmd, c):
        cmds.append(cmd)
        if cmd.startswith("sha256sum"):
            return cmd_result("", exit_code=1)
        return cmd_result()

    monkeypatch.setattr("mla.modules.copy.run_remote_cmd", fake_run)
    ssh = MagicMock()

    Copy(
        {"src": str(one_file), "dest": "/dst", "backup": True}
    ).process(ssh)

    assert any("test -e" in c and "cp -a" in c for c in cmds)
