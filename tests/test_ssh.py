from unittest.mock import MagicMock, patch

import paramiko
import pytest

from mla.inventory import Host
from mla.ssh import (
    CmdResult,
    SSHConnectionError,
    _build_connect_kwargs,
    connect,
    run_remote_cmd,
)


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


# --- connect() : on remplace paramiko.SSHClient par un faux ---------------

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
    )


def test_connect_wraps_ssh_exception():
    host = Host(name="w", address="1.2.3.4")
    fake_client = MagicMock()
    fake_client.connect.side_effect = paramiko.AuthenticationException("nope")

    with patch("mla.ssh.paramiko.SSHClient", return_value=fake_client):
        with pytest.raises(SSHConnectionError, match="1.2.3.4"):
            connect(host)


def test_connect_wraps_os_error():
    host = Host(name="w", address="1.2.3.4")
    fake_client = MagicMock()
    fake_client.connect.side_effect = OSError("unreachable")

    with patch("mla.ssh.paramiko.SSHClient", return_value=fake_client):
        with pytest.raises(SSHConnectionError, match="1.2.3.4"):
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
