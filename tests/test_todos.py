import logging
from unittest.mock import MagicMock

import pytest

from mla.inventory import Host
from mla.modules.base import ModuleError, ModuleResult
from mla.ssh import SSHConnectionError
from mla.todos import (
    HostReport,
    Todo,
    TodosError,
    _format_params,
    load_todos,
    run_todos,
)


def test_missing_file():
    with pytest.raises(TodosError):
        load_todos("tests/fixtures/does_not_exist.yml")


def test_invalid_yaml(tmp_path):
    f = tmp_path / "todos.yml"
    f.write_text("- module: [this is not: valid yaml")
    with pytest.raises(TodosError):
        load_todos(str(f))


def test_empty_file(tmp_path):
    f = tmp_path / "todos.yml"
    f.write_text("")
    with pytest.raises(TodosError):
        load_todos(str(f))


def test_root_is_not_a_list(tmp_path):
    f = tmp_path / "todos.yml"
    f.write_text("module: apt\n")
    with pytest.raises(TodosError):
        load_todos(str(f))


def test_item_is_not_a_dict(tmp_path):
    f = tmp_path / "todos.yml"
    f.write_text("- apt\n")
    with pytest.raises(TodosError):
        load_todos(str(f))


def test_item_missing_module_key(tmp_path):
    f = tmp_path / "todos.yml"
    f.write_text("- params:\n    name: nginx\n")
    with pytest.raises(TodosError):
        load_todos(str(f))


def test_params_is_not_a_dict(tmp_path):
    f = tmp_path / "todos.yml"
    f.write_text("- module: apt\n  params: nginx\n")
    with pytest.raises(TodosError):
        load_todos(str(f))


def test_params_defaults_to_empty_dict(tmp_path):
    f = tmp_path / "todos.yml"
    f.write_text("- module: command\n")

    todos = load_todos(str(f))

    assert todos == [Todo(module="command", params={})]


def test_valid_playbook_returns_expected_todos():
    todos = load_todos("tests/fixtures/todos_ok.yml")

    assert todos == [
        Todo(
            module="apt",
            params={"name": "nginx-common", "state": "present"},
        ),
        Todo(
            module="copy",
            params={
                "src": "./public",
                "dest": "/var/www/public",
                "backup": True,
            },
        ),
        Todo(
            module="service",
            params={"name": "nginx", "state": "started"},
        ),
    ]


# --- _format_params ------------------------------------------------------


def test_format_params_simple_values():
    out = _format_params({"name": "nginx", "state": "present"})

    assert out == "name=nginx state=present"


def test_format_params_flattens_multiline_values():
    out = _format_params({"command": "touch /tmp/x\ntest -f /tmp/x\n"})

    assert out == "command=touch /tmp/x test -f /tmp/x"


def test_format_params_empty():
    assert _format_params({}) == ""


# --- run_todos ------------------------------------------------------------


def make_host(address, name=None):
    return Host(name=name or address, address=address, port=22)


def make_module(changed=False, error=None, calls=None):
    """
    Fabrique une classe de module factice.

    - `changed` : valeur de ModuleResult.changed renvoyée par process()
    - `error`   : si non None, process() lève ModuleError(error)
    - `calls`   : si une liste est passée, chaque process() y ajoute
                  un tuple (params, dry_run)
    """
    class _FakeModule:
        def __init__(self, params):
            self.params = params

        def process(self, ssh_client, dry_run=False):
            if calls is not None:
                calls.append((self.params, dry_run))
            if error is not None:
                raise ModuleError(error)
            return ModuleResult(changed=changed)

    return _FakeModule


@pytest.fixture
def fake_connect(monkeypatch):
    """Remplace ssh.connect par un faux qui renvoie un MagicMock par host."""
    clients = {}

    def _connect(host):
        client = MagicMock()
        clients[host.address] = client
        return client

    monkeypatch.setattr("mla.ssh.connect", _connect)
    return clients


def test_registry_none_raises():
    with pytest.raises(TodosError):
        run_todos([Todo(module="fake")], [make_host("10.0.0.1")])


def test_unknown_module_raises(fake_connect):
    registry = {"fake": make_module()}
    todos = [Todo(module="does_not_exist")]

    with pytest.raises(TodosError, match="module inconnu"):
        run_todos(todos, [make_host("10.0.0.1")], registry=registry)

    assert fake_connect == {}  # aucune connexion ouverte avant la validation


def test_unknown_module_is_detected_even_after_valid_ones(fake_connect):
    registry = {"fake": make_module()}
    todos = [Todo(module="fake"), Todo(module="typo")]

    with pytest.raises(TodosError, match="typo"):
        run_todos(todos, [make_host("10.0.0.1")], registry=registry)


def test_returns_host_report_per_host(fake_connect):
    registry = {"fake": make_module(changed=False)}
    hosts = [make_host("10.0.0.1"), make_host("10.0.0.2")]

    reports = run_todos([Todo(module="fake")], hosts, registry=registry)

    assert set(reports) == {"10.0.0.1", "10.0.0.2"}
    assert isinstance(reports["10.0.0.1"], HostReport)


def test_ok_and_changed_are_counted(fake_connect):
    registry = {
        "keep": make_module(changed=False),
        "change": make_module(changed=True),
    }
    todos = [Todo(module="keep"), Todo(module="change"), Todo(module="change")]

    reports = run_todos(todos, [make_host("10.0.0.1")], registry=registry)

    assert reports["10.0.0.1"] == HostReport(ok=1, changed=2, fail=0)


def test_module_error_is_counted_as_fail(fake_connect, caplog):
    caplog.set_level(logging.INFO)
    registry = {"boom": make_module(error="something went very wrong")}

    reports = run_todos([Todo(module="boom")], [make_host("10.0.0.1")],
                        registry=registry)

    assert reports["10.0.0.1"] == HostReport(ok=0, changed=0, fail=1)
    assert "status=KO" in caplog.text
    assert "something went very wrong" in caplog.text


def test_error_output_is_truncated_to_200_chars(fake_connect, caplog):
    caplog.set_level(logging.INFO)
    long_msg = "x" * 500
    registry = {"boom": make_module(error=long_msg)}

    run_todos([Todo(module="boom")], [make_host("10.0.0.1")],
              registry=registry)

    assert "x" * 200 in caplog.text
    assert "x" * 201 not in caplog.text


def test_processing_and_done_lines(fake_connect, caplog):
    caplog.set_level(logging.INFO)
    registry = {"fake": make_module()}
    hosts = [make_host("10.0.0.1"), make_host("10.0.0.2")]

    run_todos([Todo(module="fake"), Todo(module="fake")], hosts,
              registry=registry)

    assert "processing 2 tasks on hosts: 10.0.0.1, 10.0.0.2" in caplog.text
    assert "done processing tasks for hosts: 10.0.0.1, 10.0.0.2" in caplog.text


def test_announce_line_contains_params_in_order(fake_connect, caplog):
    caplog.set_level(logging.INFO)
    registry = {"apt": make_module()}
    todo = Todo(module="apt", params={"name": "nginx", "state": "present"})

    run_todos([todo], [make_host("10.0.0.1")], registry=registry)

    assert (
        "[1] host=10.0.0.1 op=apt name=nginx state=present" in caplog.text
    )


def test_announce_line_without_params_has_no_trailing_space(fake_connect,
                                                            caplog):
    caplog.set_level(logging.INFO)
    registry = {"fake": make_module()}

    run_todos([Todo(module="fake")], [make_host("10.0.0.1")],
              registry=registry)

    assert "[1] host=10.0.0.1 op=fake" in caplog.messages
    assert "[1] host=10.0.0.1 op=fake " not in caplog.messages


def test_status_and_summary_lines(fake_connect, caplog):
    caplog.set_level(logging.INFO)
    registry = {
        "keep": make_module(changed=False),
        "change": make_module(changed=True),
    }

    run_todos([Todo(module="keep"), Todo(module="change")],
              [make_host("10.0.0.1")], registry=registry)

    assert "[1] host=10.0.0.1 op=keep status=OK" in caplog.text
    assert "[2] host=10.0.0.1 op=change status=CHANGED" in caplog.text
    assert "host=10.0.0.1 ok=1 changed=1 fail=0" in caplog.text


def test_failed_connection_marks_all_todos_as_fail(monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    def _connect(host):
        if host.address == "10.0.0.2":
            raise SSHConnectionError("connexion refusée")
        return MagicMock()

    monkeypatch.setattr("mla.ssh.connect", _connect)
    registry = {"fake": make_module(changed=True)}
    hosts = [make_host("10.0.0.1"), make_host("10.0.0.2")]

    reports = run_todos([Todo(module="fake"), Todo(module="fake")], hosts,
                        registry=registry)

    assert reports["10.0.0.1"] == HostReport(ok=0, changed=2, fail=0)
    assert reports["10.0.0.2"] == HostReport(ok=0, changed=0, fail=2)
    assert "host=10.0.0.2 ok=0 changed=0 fail=2" in caplog.text


def test_clients_are_closed_at_the_end(fake_connect):
    registry = {"fake": make_module()}
    hosts = [make_host("10.0.0.1"), make_host("10.0.0.2")]

    run_todos([Todo(module="fake")], hosts, registry=registry)

    for client in fake_connect.values():
        client.close.assert_called_once()


def test_clients_are_closed_even_if_a_module_crashes(fake_connect):
    registry = {"boom": make_module(error="boom")}

    run_todos([Todo(module="boom")], [make_host("10.0.0.1")],
              registry=registry)

    fake_connect["10.0.0.1"].close.assert_called_once()


def test_dry_run_is_forwarded_to_modules(fake_connect):
    calls = []
    registry = {"fake": make_module(calls=calls)}

    run_todos([Todo(module="fake", params={"a": 1})],
              [make_host("10.0.0.1")], registry=registry, dry_run=True)

    assert calls == [({"a": 1}, True)]
