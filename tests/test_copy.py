import hashlib
import logging
from unittest.mock import MagicMock

import pytest

from mla.modules import MODULES
from mla.modules.base import ModuleError, ModuleResult, sudo_cmd
from mla.modules.copy import Copy, local_mode
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
    with pytest.raises(ModuleError, match="not found"):
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

TMPDIR = "/tmp/tmp.mla42"
PASSWORD = "s3cret"


@pytest.fixture
def one_file(tmp_path):
    f = tmp_path / "index.html"
    f.write_text("hello")
    f.chmod(0o640)
    return f


def make_ssh():
    """
    Faux SSHClient dont 'with open_sftp() as sftp' renvoie le même sftp.
    Retourne (ssh, sftp).
    """
    ssh = MagicMock()
    sftp = ssh.open_sftp.return_value
    sftp.__enter__.return_value = sftp
    return ssh, sftp


def patch_run(monkeypatch, remote_hash=None, fail_on=None):
    """
    Faux run_remote_cmd branché sur copy et base :
    - 'sha256sum' -> 'remote_hash' (None => fichier absent)
    - 'mktemp -d' -> TMPDIR
    - toute commande contenant 'fail_on' -> exit 1
    Retourne la liste des commandes vues.
    """
    calls = []

    def fake_run(cmd, c):
        calls.append(cmd)
        if fail_on and fail_on in cmd:
            return CmdResult("", f"{fail_on}: boom", 1)
        if cmd.startswith("sha256sum"):
            if remote_hash is None:
                return cmd_result("", exit_code=1)
            return cmd_result(f"{remote_hash}  x\n")
        if cmd == "mktemp -d":
            return cmd_result(TMPDIR + "\n")
        return cmd_result()

    monkeypatch.setattr("mla.modules.copy.run_remote_cmd", fake_run)
    monkeypatch.setattr("mla.modules.base.run_remote_cmd", fake_run)
    return calls


def test_local_mode(one_file):
    assert local_mode(str(one_file)) == "0640"


def test_process_no_change_skips_sftp(one_file, monkeypatch):
    patch_run(monkeypatch, remote_hash=Copy._sha256_local(str(one_file)))
    ssh, _ = make_ssh()

    result = Copy({"src": str(one_file), "dest": "/dst"}).process(ssh)

    assert result == ModuleResult(changed=False)
    ssh.open_sftp.assert_not_called()


def test_process_dry_run_does_not_copy(one_file, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    patch_run(monkeypatch)
    ssh, _ = make_ssh()

    result = Copy({"src": str(one_file), "dest": "/dst"}).process(
        ssh, dry_run=True)

    assert result == ModuleResult(changed=True)
    ssh.open_sftp.assert_not_called()


# --- sans sudo : mkdir -p + put direct


def test_process_without_sudo_puts_directly(one_file, monkeypatch):
    calls = patch_run(monkeypatch)
    ssh, sftp = make_ssh()

    result = Copy(
        {"src": str(one_file), "dest": "/dst/index.html"}
    ).process(ssh)

    assert result == ModuleResult(changed=True)
    sftp.put.assert_called_once_with(str(one_file), "/dst/index.html")
    sftp.__exit__.assert_called_once()
    assert "mkdir -p /dst" in calls
    assert not any("sudo" in c or "mktemp" in c for c in calls)


def test_process_without_sudo_mkdir_failure_raises(one_file, monkeypatch):
    patch_run(monkeypatch, fail_on="mkdir")
    ssh, sftp = make_ssh()

    with pytest.raises(ModuleError, match="mkdir"):
        Copy({"src": str(one_file), "dest": "/dst/index.html"}).process(ssh)

    sftp.put.assert_not_called()


# --- avec sudo : mktemp + put + un seul sudo install -D + rm


def test_process_with_sudo_stages_and_installs(one_file, monkeypatch):
    calls = patch_run(monkeypatch)
    ssh, sftp = make_ssh()

    result = Copy(
        {"src": str(one_file), "dest": "/var/www/index.html"}
    ).process(ssh, sudo_password=PASSWORD)

    assert result == ModuleResult(changed=True)
    sftp.put.assert_called_once_with(str(one_file), f"{TMPDIR}/0")
    install = sudo_cmd(
        f"install -D -m 0640 {TMPDIR}/0 /var/www/index.html", PASSWORD)
    assert calls[-3:] == ["mktemp -d", install, f"rm -rf {TMPDIR}"]
    assert not any(c.startswith("mkdir") for c in calls)


def test_process_with_sudo_directory_uses_one_sudo(tmp_path, monkeypatch):
    src = tmp_path / "public"
    (src / "css").mkdir(parents=True)
    (src / "index.html").write_text("a")
    (src / "css" / "site.css").write_text("b")
    calls = patch_run(monkeypatch)
    ssh, sftp = make_ssh()

    Copy({"src": str(src), "dest": "/var/www/public"}).process(
        ssh, sudo_password=PASSWORD)

    sudo = [c for c in calls if "sudo" in c]
    assert len(sudo) == 1
    assert sudo[0].count("install -D") == 2
    assert " && " in sudo[0]
    assert sftp.put.call_count == 2


def test_process_with_sudo_install_failure_still_cleans_up(one_file,
                                                           monkeypatch):
    calls = patch_run(monkeypatch, fail_on="install -D")
    ssh, _ = make_ssh()

    with pytest.raises(ModuleError, match="install"):
        Copy({"src": str(one_file), "dest": "/dst/index.html"}).process(
            ssh, sudo_password=PASSWORD)

    assert calls[-1] == f"rm -rf {TMPDIR}"


def test_process_with_sudo_put_failure_still_cleans_up(one_file,
                                                       monkeypatch):
    calls = patch_run(monkeypatch)
    ssh, sftp = make_ssh()
    sftp.put.side_effect = OSError("no space left")

    with pytest.raises(OSError):
        Copy({"src": str(one_file), "dest": "/dst/index.html"}).process(
            ssh, sudo_password=PASSWORD)

    assert calls[-1] == f"rm -rf {TMPDIR}"


def test_process_with_sudo_cleanup_failure_raises(one_file, monkeypatch):
    patch_run(monkeypatch, fail_on="rm -rf")
    ssh, _ = make_ssh()

    with pytest.raises(ModuleError, match="cleanup"):
        Copy({"src": str(one_file), "dest": "/dst/index.html"}).process(
            ssh, sudo_password=PASSWORD)


def test_process_mktemp_failure_raises(one_file, monkeypatch):
    patch_run(monkeypatch, fail_on="mktemp")
    ssh, sftp = make_ssh()

    with pytest.raises(ModuleError, match="mktemp"):
        Copy({"src": str(one_file), "dest": "/dst/index.html"}).process(
            ssh, sudo_password=PASSWORD)

    sftp.put.assert_not_called()


# --- backup


def test_process_backup_without_sudo(one_file, monkeypatch):
    calls = patch_run(monkeypatch)
    ssh, _ = make_ssh()

    Copy(
        {"src": str(one_file), "dest": "/dst", "backup": True}
    ).process(ssh)

    backup = [c for c in calls if "cp -a" in c]
    assert len(backup) == 1
    assert backup[0].startswith("if [ -e /dst ]; then cp -a /dst /dst.")
    assert "sudo" not in backup[0]


def test_process_backup_with_sudo(one_file, monkeypatch):
    calls = patch_run(monkeypatch)
    ssh, _ = make_ssh()

    Copy(
        {"src": str(one_file), "dest": "/dst", "backup": True}
    ).process(ssh, sudo_password=PASSWORD)

    backup = [c for c in calls if "cp -a" in c]
    assert len(backup) == 1
    assert backup[0].startswith("printf ")
    assert "sudo -S -p ''" in backup[0]


def test_process_backup_failure_raises(one_file, monkeypatch):
    patch_run(monkeypatch, fail_on="cp -a")
    ssh, sftp = make_ssh()

    with pytest.raises(ModuleError, match="cp -a"):
        Copy(
            {"src": str(one_file), "dest": "/dst", "backup": True}
        ).process(ssh)

    sftp.put.assert_not_called()
