from unittest.mock import MagicMock, patch

import paramiko
import pytest

from mla.inventory import Host
from mla.ssh import (
    CmdResult,
    SSHConnectionError,
    _build_connect_kwargs,
    _resolve_target,
    connect,
    load_ssh_config,
    run_remote_cmd,
)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """HOME vide : le ~/.ssh/config réel ne doit pas influencer les tests."""
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def write_ssh_config(home, text):
    ssh_dir = home / ".ssh"
    ssh_dir.mkdir(exist_ok=True)
    (ssh_dir / "config").write_text(text)


# --- _build_connect_kwargs : fonction pure, pas de réseau -----------------

def test_default_auth_uses_current_user(monkeypatch):
    monkeypatch.setattr("getpass.getuser", lambda: "bob")
    host = Host(name="w", address="1.2.3.4")

    assert _build_connect_kwargs(host) == {"username": "bob"}


def test_explicit_user_is_kept_over_current_user(monkeypatch):
    monkeypatch.setattr("getpass.getuser", lambda: "bob")
    host = Host(name="w", address="1.2.3.4", user="alice")

    assert _build_connect_kwargs(host) == {"username": "alice"}


def test_password_auth():
    host = Host(name="w", address="1.2.3.4", user="alice", password="s3cret")

    assert _build_connect_kwargs(host) == {
        "username": "alice",
        "password": "s3cret",
    }


def test_key_auth():
    host = Host(name="w", address="1.2.3.4", user="alice", key_file="/tmp/k")
    kwargs = _build_connect_kwargs(host)

    assert kwargs["key_filename"] == "/tmp/k"
    assert "password" not in kwargs


def test_key_file_has_priority_over_password():
    host = Host(
        name="w", address="1.2.3.4",
        password="s3cret", key_file="/tmp/k",
    )
    kwargs = _build_connect_kwargs(host)

    assert "key_filename" in kwargs
    assert "password" not in kwargs


def test_key_file_tilde_is_expanded(monkeypatch):
    monkeypatch.setenv("HOME", "/home/tester")
    host = Host(name="w", address="1.2.3.4", user="alice",
                key_file="~/.ssh/id_ed25519")
    kwargs = _build_connect_kwargs(host)

    assert kwargs["key_filename"] == "/home/tester/.ssh/id_ed25519"


def test_config_user_is_used_when_inventory_has_none(monkeypatch):
    monkeypatch.setattr("getpass.getuser", lambda: "bob")
    host = Host(name="w", address="1.2.3.4")

    assert _build_connect_kwargs(host, {"user": "carol"}) == {
        "username": "carol"}


def test_inventory_user_beats_config_user():
    host = Host(name="w", address="1.2.3.4", user="alice")

    assert _build_connect_kwargs(host, {"user": "carol"}) == {
        "username": "alice"}


def test_config_identityfile_is_used_when_inventory_has_no_key(
        monkeypatch):
    monkeypatch.setenv("HOME", "/home/tester")
    host = Host(name="w", address="1.2.3.4", user="alice")
    kwargs = _build_connect_kwargs(
        host, {"identityfile": ["~/.ssh/cfg_key"]})

    assert kwargs["key_filename"] == "/home/tester/.ssh/cfg_key"


def test_inventory_key_beats_config_identityfile():
    host = Host(name="w", address="1.2.3.4", user="alice", key_file="/k")
    kwargs = _build_connect_kwargs(host, {"identityfile": ["/cfg"]})

    assert kwargs["key_filename"] == "/k"


# --- _resolve_target : adresse et port effectifs ---------------------------

def test_target_defaults_to_inventory_address_and_port_22():
    host = Host(name="w", address="1.2.3.4")

    assert _resolve_target(host, {}) == ("1.2.3.4", 22)


def test_target_uses_config_hostname_and_port():
    host = Host(name="w", address="web")

    assert _resolve_target(host, {"hostname": "10.0.0.5",
                                  "port": "2200"}) == ("10.0.0.5", 2200)


def test_inventory_port_beats_config_port():
    host = Host(name="w", address="web", port=2222)

    assert _resolve_target(host, {"port": "2200"}) == ("web", 2222)


# --- load_ssh_config : lecture de ~/.ssh/config ----------------------------

def test_missing_ssh_config_is_tolerated():
    assert load_ssh_config("1.2.3.4") == {}


def test_ssh_config_is_looked_up_for_the_host(isolated_home):
    write_ssh_config(isolated_home, "Host web\n    User carol\n"
                                    "    Port 2200\n")

    config = load_ssh_config("web")

    assert config["user"] == "carol"
    assert config["port"] == "2200"
    assert load_ssh_config("other").get("user") is None


# --- connect() : on remplace paramiko.SSHClient par un faux ---------------

def test_connect_applies_ssh_config(isolated_home, monkeypatch):
    monkeypatch.setattr("getpass.getuser", lambda: "bob")
    write_ssh_config(isolated_home,
                     "Host web\n    HostName 10.0.0.5\n    User carol\n"
                     "    Port 2200\n    IdentityFile ~/.ssh/cfg_key\n")
    fake_client = MagicMock()

    with patch("mla.ssh.paramiko.SSHClient", return_value=fake_client):
        connect(Host(name="w", address="web"))

    args, kwargs = fake_client.connect.call_args
    assert args == ("10.0.0.5",)
    assert kwargs["port"] == 2200
    assert kwargs["username"] == "carol"
    assert kwargs["key_filename"] == str(isolated_home / ".ssh/cfg_key")


def test_connect_uses_built_kwargs_and_sets_host_key_policy():
    host = Host(
        name="w", address="1.2.3.4", port=2222,
        user="alice", password="s3cret",
    )
    fake_client = MagicMock()

    with patch("mla.ssh.paramiko.SSHClient", return_value=fake_client):
        result = connect(host)

    assert result is fake_client
    fake_client.set_missing_host_key_policy.assert_called_once()
    policy = fake_client.set_missing_host_key_policy.call_args.args[0]
    assert isinstance(policy, paramiko.AutoAddPolicy)
    fake_client.connect.assert_called_once_with(
        "1.2.3.4", port=2222, username="alice", password="s3cret",
        timeout=10, banner_timeout=10, auth_timeout=10,
    )


def test_connect_sets_all_timeouts_to_10_seconds():
    host = Host(name="w", address="1.2.3.4")
    fake_client = MagicMock()

    with patch("mla.ssh.paramiko.SSHClient", return_value=fake_client):
        connect(host)

    kwargs = fake_client.connect.call_args.kwargs
    assert kwargs["timeout"] == 10
    assert kwargs["banner_timeout"] == 10
    assert kwargs["auth_timeout"] == 10


def test_connect_wraps_ssh_exception():
    host = Host(name="w", address="1.2.3.4")
    fake_client = MagicMock()
    fake_client.connect.side_effect = paramiko.AuthenticationException("nope")

    with patch("mla.ssh.paramiko.SSHClient", return_value=fake_client):
        with pytest.raises(SSHConnectionError, match="^nope$"):
            connect(host)


def test_connect_wraps_os_error():
    host = Host(name="w", address="1.2.3.4")
    fake_client = MagicMock()
    fake_client.connect.side_effect = OSError("unreachable")

    with patch("mla.ssh.paramiko.SSHClient", return_value=fake_client):
        with pytest.raises(SSHConnectionError, match="^unreachable$"):
            connect(host)


# --- run_remote_cmd() : on remplace le ssh_client par un faux -------------

def _fake_exec_command(stdout_data, exit_code, stderr_data=b""):
    """Construit un faux retour de `SSHClient.exec_command`."""
    fake_stdin = MagicMock()
    fake_stdout = MagicMock()
    fake_stdout.read.return_value = stdout_data
    fake_stdout.channel.recv_exit_status.return_value = exit_code
    fake_stderr = MagicMock()
    fake_stderr.read.return_value = stderr_data
    return fake_stdin, fake_stdout, fake_stderr


def test_run_remote_cmd_returns_cmdresult_on_success():
    fake_client = MagicMock()
    fake_client.exec_command.return_value = _fake_exec_command(
        b"hello\n", exit_code=0,
    )

    result = run_remote_cmd("echo hello", fake_client)

    fake_client.exec_command.assert_called_once_with("echo hello")
    assert result == CmdResult(stdout="hello\n", stderr="", exit_code=0)


def test_run_remote_cmd_reports_non_zero_exit_code():
    fake_client = MagicMock()
    fake_client.exec_command.return_value = _fake_exec_command(
        b"", exit_code=1, stderr_data=b"command not found\n",
    )

    result = run_remote_cmd("bad-cmd", fake_client)

    assert result.exit_code == 1
    assert result.stderr == "command not found\n"


def test_run_remote_cmd_sends_stdin_data_and_closes_it():
    fake_client = MagicMock()
    fake_stdin, fake_stdout, fake_stderr = _fake_exec_command(b"", 0)
    fake_client.exec_command.return_value = (
        fake_stdin, fake_stdout, fake_stderr)

    run_remote_cmd("sudo -S true", fake_client, stdin_data="s3cret\n")

    fake_client.exec_command.assert_called_once_with("sudo -S true")
    fake_stdin.write.assert_called_once_with("s3cret\n")
    fake_stdin.channel.shutdown_write.assert_called_once()


def test_run_remote_cmd_without_stdin_data_writes_nothing():
    fake_client = MagicMock()
    fake_stdin, fake_stdout, fake_stderr = _fake_exec_command(b"", 0)
    fake_client.exec_command.return_value = (
        fake_stdin, fake_stdout, fake_stderr)

    run_remote_cmd("true", fake_client)

    fake_stdin.write.assert_not_called()
