import pytest

from mla.modules import MODULES
from mla.modules.base import ModuleError, ModuleResult, sudo_cmd
from mla.modules.sysctl import CONF_FILE, Sysctl
from mla.ssh import CmdResult

ATTR = "net.core.somaxconn"
PASSWORD = "s3cret"
PERSIST_8192 = (
    f"touch {CONF_FILE} && "
    f"sed -i '/^[[:space:]]*net\\.core\\.somaxconn[[:space:]]*=/d' "
    f"{CONF_FILE} && echo '{ATTR} = 8192' >> {CONF_FILE}")


def make_run(current="0", persisted=False, w_exit=0, echo_exit=0, w_stderr=""):
    """
    Faux run_remote_cmd :
    - 'cat /proc/sys/...'  -> `current` (None => exit 1, attribut inconnu)
    - 'grep -qxF ...'      -> exit 0 si `persisted`
    - '... sysctl -w ...'  -> CmdResult('', w_stderr, w_exit)
    - le reste (echo >>)   -> exit `echo_exit`
    Retourne (fake_run, calls).
    """
    calls = []

    def fake_run(cmd, ssh_client, stdin_data=None):
        calls.append(cmd)
        if cmd.startswith("cat /proc/sys"):
            if current is None:
                return CmdResult("", "", 1)
            return CmdResult(current + "\n", "", 0)
        if cmd.startswith("grep -qxF"):
            return CmdResult("", "", 0 if persisted else 1)
        if "sysctl -w" in cmd:
            return CmdResult("", w_stderr, w_exit)
        return CmdResult("", "", echo_exit)

    return fake_run, calls


def run_sysctl(monkeypatch, params, dry_run=False, sudo_password=None,
               **run_kw):
    fake_run, calls = make_run(**run_kw)
    monkeypatch.setattr("mla.modules.sysctl.run_remote_cmd", fake_run)
    monkeypatch.setattr("mla.modules.base.run_remote_cmd", fake_run)
    result = Sysctl(params).process(object(), dry_run=dry_run,
                                    sudo_password=sudo_password)
    return result, calls


def sudo_calls(calls):
    return [c for c in calls if c.startswith("sudo")]


def test_registry_exposes_sysctl():
    assert MODULES["sysctl"] is Sysctl


# --- _params -------------------------------------------------------------


def test_params_missing_attribute_raises():
    with pytest.raises(ModuleError, match="attribute"):
        Sysctl({"value": 1})._params()


def test_params_missing_value_raises():
    with pytest.raises(ModuleError, match="value"):
        Sysctl({"attribute": ATTR})._params()


def test_params_value_zero_is_accepted():
    assert Sysctl({"attribute": ATTR, "value": 0})._params() == (ATTR, "0",
                                                                 False)


def test_params_value_is_stringified_and_permanent_defaults_false():
    assert Sysctl({"attribute": ATTR, "value": 8192})._params() == (
        ATTR, "8192", False)


# --- _current_value ------------------------------------------------


def test_current_value_reads_proc_sys(monkeypatch):
    seen = []

    def fake(cmd, c, stdin_data=None):
        seen.append(cmd)
        return CmdResult("4096\n", "", 0)

    monkeypatch.setattr("mla.modules.sysctl.run_remote_cmd", fake)

    assert Sysctl({})._current_value(object(), ATTR) == "4096"
    assert seen == ["cat /proc/sys/net/core/somaxconn"]


def test_current_value_none_when_unknown(monkeypatch):
    monkeypatch.setattr("mla.modules.sysctl.run_remote_cmd",
                        lambda cmd, c: CmdResult("", "err", 1))
    assert Sysctl({})._current_value(object(), ATTR) is None


# --- process ---------------------------------------------------------


def test_runtime_already_set_no_permanent_is_ok(monkeypatch):
    result, calls = run_sysctl(
        monkeypatch, {"attribute": ATTR, "value": 8192}, current="8192")

    assert result == ModuleResult(changed=False)
    assert sudo_calls(calls) == []


def test_runtime_differs_sets_it(monkeypatch):
    result, calls = run_sysctl(
        monkeypatch, {"attribute": ATTR, "value": 8192},
        sudo_password=PASSWORD, current="128")

    assert result == ModuleResult(changed=True)
    assert sudo_calls(calls) == [
        sudo_cmd(f"sysctl -w {ATTR}=8192")]


def test_permanent_line_present_is_ok(monkeypatch):
    result, calls = run_sysctl(
        monkeypatch,
        {"attribute": ATTR, "value": 8192, "permanent": True},
        current="8192", persisted=True)

    assert result == ModuleResult(changed=False)
    assert sudo_calls(calls) == []


def test_permanent_line_absent_writes_file_only(monkeypatch):
    result, calls = run_sysctl(
        monkeypatch,
        {"attribute": ATTR, "value": 8192, "permanent": True},
        sudo_password=PASSWORD, current="8192", persisted=False)

    assert result == ModuleResult(changed=True)
    sudo = sudo_calls(calls)
    assert len(sudo) == 1
    assert "sudo -S -p '' sh -c " in sudo[0]
    assert CONF_FILE in sudo[0]
    assert "sysctl -w" not in sudo[0]


def test_permanent_runtime_and_file_both_updated(monkeypatch):
    result, calls = run_sysctl(
        monkeypatch,
        {"attribute": ATTR, "value": 8192, "permanent": True},
        sudo_password=PASSWORD, current="128", persisted=False)

    assert result == ModuleResult(changed=True)
    sudo = sudo_calls(calls)
    assert any("sysctl -w" in c for c in sudo)
    assert any("sh -c" in c and CONF_FILE in c for c in sudo)


def test_sysctl_w_failure_raises(monkeypatch):
    with pytest.raises(ModuleError, match="operation not permitted"):
        run_sysctl(monkeypatch, {"attribute": ATTR, "value": 8192},
                   sudo_password=PASSWORD, current="128", w_exit=1,
                   w_stderr="operation not permitted")


def test_sysctl_w_failure_without_output_mentions_code(monkeypatch):
    with pytest.raises(ModuleError, match="255"):
        run_sysctl(monkeypatch, {"attribute": ATTR, "value": 8192},
                   sudo_password=PASSWORD, current="128", w_exit=255)


def test_missing_sudo_password_raises_when_change_needed(monkeypatch):
    with pytest.raises(ModuleError, match="sudo password"):
        run_sysctl(monkeypatch, {"attribute": ATTR, "value": 8192},
                   current="128")


def test_dry_run_executes_nothing(monkeypatch):
    result, calls = run_sysctl(
        monkeypatch, {"attribute": ATTR, "value": 8192},
        dry_run=True, current="128")

    assert result == ModuleResult(changed=True,
                                  commands=[f"sysctl -w {ATTR}=8192"])
    assert sudo_calls(calls) == []


def test_dry_run_lists_only_needed_commands(monkeypatch):
    result, _ = run_sysctl(
        monkeypatch, {"attribute": ATTR, "value": 8192, "permanent": True},
        dry_run=True, current="8192", persisted=False)

    assert result.commands == [PERSIST_8192]


def test_dry_run_lists_runtime_and_permanent(monkeypatch):
    result, _ = run_sysctl(
        monkeypatch, {"attribute": ATTR, "value": 8192, "permanent": True},
        dry_run=True, current="128", persisted=False)

    assert result.commands == [f"sysctl -w {ATTR}=8192", PERSIST_8192]


# --- E10 : booléens, valeurs multiples, pas de doublon dans le .conf ------


@pytest.mark.parametrize("raw, expected", [(True, "1"), (False, "0")])
def test_params_bool_value_becomes_1_or_0(raw, expected):
    _, value, _ = Sysctl({"attribute": "net.ipv4.ip_forward",
                          "value": raw})._params()

    assert value == expected


def test_params_multi_value_whitespace_is_normalized():
    _, value, _ = Sysctl({"attribute": "net.ipv4.ip_local_port_range",
                          "value": "32768   60999"})._params()

    assert value == "32768 60999"


def test_multi_value_with_tab_in_proc_is_idempotent(monkeypatch):
    result, calls = run_sysctl(
        monkeypatch,
        {"attribute": "net.ipv4.ip_local_port_range", "value": "32768 60999"},
        current="32768\t60999")

    assert result == ModuleResult(changed=False)
    assert sudo_calls(calls) == []


def test_bool_true_sets_1(monkeypatch):
    _, calls = run_sysctl(
        monkeypatch, {"attribute": "net.ipv4.ip_forward", "value": True},
        sudo_password=PASSWORD, current="0")

    assert sudo_calls(calls) == [sudo_cmd("sysctl -w net.ipv4.ip_forward=1")]


def test_permanent_write_removes_previous_lines_for_attribute(monkeypatch):
    _, calls = run_sysctl(
        monkeypatch,
        {"attribute": ATTR, "value": 1024, "permanent": True},
        sudo_password=PASSWORD, current="1024", persisted=False)

    write = sudo_calls(calls)[0]
    assert "sed -i" in write
    assert r"net\.core\.somaxconn" in write
    assert write.index("sed -i") < write.index(">> " + CONF_FILE)
