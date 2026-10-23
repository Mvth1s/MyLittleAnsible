import ast
import pathlib
import subprocess
import sys

# stdlib + libs autorisées par le sujet (pyyaml s'importe 'yaml')
ALLOWED = set(sys.stdlib_module_names) | {
    "paramiko", "jinja2", "click", "docopt", "yaml", "mla"}


def imported_top_level_modules():
    for path in pathlib.Path("mla").rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    yield path, alias.name.split(".")[0]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                yield path, node.module.split(".")[0]


def test_only_allowed_libraries_are_imported():
    forbidden = {(str(path), name)
                 for path, name in imported_top_level_modules()
                 if name not in ALLOWED}

    assert forbidden == set()


def test_importing_mla_emits_no_warning():
    result = subprocess.run(
        [sys.executable, "-W", "default", "-c", "import mla.cli"],
        capture_output=True, text=True, check=True)

    assert result.stderr == ""
