import logging

import pytest

from mla.modules import MODULES
from mla.modules.base import ModuleError, ModuleResult
from mla.modules.service import Service
from mla.ssh import CmdResult


def make_run(active=False, enabled=False, action_exit=0, action_stderr=""):
    """
    Faux run_remote_cmd :
    - 'systemctl is-active ...'  -> exit 0 si `active`
    - 'systemctl is-enabled ...' -> exit 0 si `enabled`
    - le reste (l'action sudo)   -> CmdResult('', action_stderr, action_exit)
    Retourne (fake_run, calls).
    """
    calls = []

    def fake_run(cmd, ssh_client):
        calls.append(cmd)
        if "is-active" in cmd:
            return CmdResult("", "", 0 if active else 1)
        if "is-enabled" in cmd:
            return CmdResult("", "", 0 if enabled else 1)
        return CmdResult("", action_stderr, action_exit)

    return fake_run, calls


def run_service(monkeypatch, params, dry_run=False, **run_kw):
    fake_run, calls = make_run(**run_kw)
    monkeypatch.setattr("mla.modules.service.run_remote_cmd", fake_run)
    result = Service(params).process(object(), dry_run=dry_run)
    return result, calls


def action_calls(calls):
    return [c for c in calls if c.startswith("sudo -n systemctl")]


def test_registry_exposes_service():
    assert MODULES["service"] is Service


# --- _params -------------------------------------------------------------


def test_params_missing_name_raises():
    with pytest.raises(ModuleError, match="name"):
        Service({"state": "started"})._params()


def test_params_missing_state_raises():
    with pytest.raises(ModuleError, match="state"):
        Service({"name": "nginx"})._params()


def test_params_invalid_state_raises():
    with pytest.raises(ModuleError, match="state"):
        Service({"name": "nginx", "state": "reloaded"})._params()


def test_params_valid():
    assert Service({"name": "nginx", "state": "started"})._params() == (
        "nginx", "started")


# --- started / stopped -------------------------------------------------


def test_started_when_inactive_starts(monkeypatch):
    result, calls = run_service(
        monkeypatch, {"name": "nginx", "state": "started"}, active=False)

    assert result == ModuleResult(changed=True)
    assert action_calls(calls) == ["sudo -n systemctl start nginx"]


def test_started_when_active_is_ok(monkeypatch):
    result, calls = run_service(
        monkeypatch, {"name": "nginx", "state": "started"}, active=True)

    assert result == ModuleResult(changed=False)
    assert action_calls(calls) == []


def test_stopped_when_active_stops(monkeypatch):
    result, calls = run_service(
        monkeypatch, {"name": "nginx", "state": "stopped"}, active=True)

    assert result == ModuleResult(changed=True)
    assert action_calls(calls) == ["sudo -n systemctl stop nginx"]


def test_stopped_when_inactive_is_ok(monkeypatch):
    result, calls = run_service(
        monkeypatch, {"name": "nginx", "state": "stopped"}, active=False)

    assert result == ModuleResult(changed=False)
    assert action_calls(calls) == []


# --- restarted : toujours CHANGED ------------------------------------


def test_restarted_when_active(monkeypatch):
    result, calls = run_service(
        monkeypatch, {"name": "nginx", "state": "restarted"}, active=True)

    assert result == ModuleResult(changed=True)
    assert action_calls(calls) == ["sudo -n systemctl restart nginx"]


def test_restarted_when_inactive_still_changed(monkeypatch):
    result, calls = run_service(
        monkeypatch, {"name": "nginx", "state": "restarted"}, active=False)

    assert result == ModuleResult(changed=True)
    assert any("is-active" not in c for c in calls)


# --- enabled / disabled ---------------------------------------------


def test_enabled_when_disabled_enables(monkeypatch):
    result, calls = run_service(
        monkeypatch, {"name": "nginx", "state": "enabled"}, enabled=False)

    assert result == ModuleResult(changed=True)
    assert action_calls(calls) == ["sudo -n systemctl enable nginx"]


def test_enabled_when_enabled_is_ok(monkeypatch):
    result, calls = run_service(
        monkeypatch, {"name": "nginx", "state": "enabled"}, enabled=True)

    assert result == ModuleResult(changed=False)
    assert action_calls(calls) == []


def test_disabled_when_enabled_disables(monkeypatch):
    result, calls = run_service(
        monkeypatch, {"name": "nginx", "state": "disabled"}, enabled=True)

    assert result == ModuleResult(changed=True)
    assert action_calls(calls) == ["sudo -n systemctl disable nginx"]


def test_disabled_when_disabled_is_ok(monkeypatch):
    result, calls = run_service(
        monkeypatch, {"name": "nginx", "state": "disabled"}, enabled=False)

    assert result == ModuleResult(changed=False)
    assert action_calls(calls) == []


# --- échec / dry-run ------------------------------------------------


def test_action_failure_raises_module_error(monkeypatch):
    with pytest.raises(ModuleError, match="permission"):
        run_service(monkeypatch, {"name": "nginx", "state": "started"},
                    active=False, action_exit=1,
                    action_stderr="permission denied")


def test_action_failure_without_output_mentions_code(monkeypatch):
    with pytest.raises(ModuleError, match="5"):
        run_service(monkeypatch, {"name": "nginx", "state": "started"},
                    active=False, action_exit=5)


def test_dry_run_does_not_execute(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    result, calls = run_service(
        monkeypatch, {"name": "nginx", "state": "started"},
        dry_run=True, active=False)

    assert result == ModuleResult(changed=True)
    assert action_calls(calls) == []
    assert "sudo -n systemctl start nginx" in caplog.text
