import pytest

from mla.todos import Todo, TodosError, load_todos


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
