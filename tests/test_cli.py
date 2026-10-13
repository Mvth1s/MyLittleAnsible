import pytest
from click.testing import CliRunner

from mla.cli import main
from mla.inventory import InventoryError
from mla.modules import MODULES
from mla.todos import HostReport


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def wired(monkeypatch):
    """
    Remplace toutes les dépendances de cli.main par des faux et enregistre
    les appels dans le dict renvoyé.
    """
    calls = {"order": []}

    def fake_configure_logging(debug=False):
        calls["order"].append("configure_logging")
        calls["debug"] = debug

    def fake_load_inventory(path):
        calls["order"].append("load_inventory")
        calls["inventory_path"] = path
        return ["<host>"]

    def fake_load_todos(path):
        calls["order"].append("load_todos")
        calls["todos_path"] = path
        return ["<todo>"]

    def fake_run_todos(todos, hosts, registry, dry_run):
        calls["order"].append("run_todos")
        calls["run_todos"] = {
            "todos": todos,
            "hosts": hosts,
            "registry": registry,
            "dry_run": dry_run,
        }
        return calls.get("reports", {"10.0.0.1": HostReport()})

    monkeypatch.setattr("mla.cli.configure_logging", fake_configure_logging)
    monkeypatch.setattr("mla.cli.load_inventory", fake_load_inventory)
    monkeypatch.setattr("mla.cli.load_todos", fake_load_todos)
    monkeypatch.setattr("mla.cli.run_todos", fake_run_todos)
    return calls


def test_help_exits_zero(runner):
    result = runner.invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "-f" in result.output
    assert "-i" in result.output


def test_f_flag_is_required(runner, wired):
    result = runner.invoke(main, ["-i", "inv.yml"])

    assert result.exit_code == 2
    assert "-f" in result.output


def test_i_flag_is_required(runner, wired):
    result = runner.invoke(main, ["-f", "todos.yml"])

    assert result.exit_code == 2
    assert "-i" in result.output


def test_paths_are_passed_to_the_loaders(runner, wired):
    runner.invoke(main, ["-f", "todos.yml", "-i", "inv.yml"])

    assert wired["todos_path"] == "todos.yml"
    assert wired["inventory_path"] == "inv.yml"


def test_logging_is_configured_before_anything_else(runner, wired):
    runner.invoke(main, ["-f", "t", "-i", "i"])

    assert wired["order"][0] == "configure_logging"


def test_debug_defaults_to_false(runner, wired):
    runner.invoke(main, ["-f", "t", "-i", "i"])

    assert wired["debug"] is False


def test_debug_flag_is_forwarded(runner, wired):
    runner.invoke(main, ["-f", "t", "-i", "i", "--debug"])

    assert wired["debug"] is True


def test_dry_run_defaults_to_false(runner, wired):
    runner.invoke(main, ["-f", "t", "-i", "i"])

    assert wired["run_todos"]["dry_run"] is False


def test_dry_run_flag_is_forwarded(runner, wired):
    runner.invoke(main, ["-f", "t", "-i", "i", "--dry-run"])

    assert wired["run_todos"]["dry_run"] is True


def test_loaded_hosts_and_todos_go_to_run_todos(runner, wired):
    runner.invoke(main, ["-f", "t", "-i", "i"])

    assert wired["run_todos"]["todos"] == ["<todo>"]
    assert wired["run_todos"]["hosts"] == ["<host>"]


def test_module_registry_is_passed_to_run_todos(runner, wired):
    runner.invoke(main, ["-f", "t", "-i", "i"])

    assert wired["run_todos"]["registry"] is MODULES


def test_exit_zero_when_no_host_failed(runner, wired):
    wired["reports"] = {"10.0.0.1": HostReport(ok=3, changed=1, fail=0)}

    result = runner.invoke(main, ["-f", "t", "-i", "i"])

    assert result.exit_code == 0


def test_exit_one_when_a_host_failed(runner, wired):
    wired["reports"] = {
        "10.0.0.1": HostReport(ok=1, changed=0, fail=0),
        "10.0.0.2": HostReport(ok=0, changed=0, fail=2),
    }

    result = runner.invoke(main, ["-f", "t", "-i", "i"])

    assert result.exit_code == 1


def test_inventory_error_is_not_swallowed(runner, monkeypatch):
    def boom(path):
        raise InventoryError("inventory introuvable : x")

    monkeypatch.setattr("mla.cli.configure_logging", lambda debug=False: None)
    monkeypatch.setattr("mla.cli.load_inventory", boom)

    result = runner.invoke(main, ["-f", "t", "-i", "i"])

    assert isinstance(result.exception, InventoryError)
