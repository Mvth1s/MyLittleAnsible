"""
Lecture du playbook (todos.yml) et orchestration des todos.
"""

from dataclasses import dataclass, field

import yaml


class TodosError(Exception):
    """
    Playbook absent, illisible ou mal formé.
    """


@dataclass
class Todo:
    module: str
    params: dict = field(default_factory=dict)


def load_todos(path):
    """
    Lit 'path' (YAML) et retourne la liste des Todo.

    Lève TodosError si le fichier est absent, invalide ou mal structuré.
    """
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        raise TodosError(f"playbook introuvable : {path}") from None
    except yaml.YAMLError as exc:
        raise TodosError(f"playbook YAML invalide : {exc}") from exc

    if not isinstance(data, list):
        raise TodosError("playbook invalide : la racine doit être une liste")

    todos = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise TodosError(f"todo {index} : définition invalide")
        if "module" not in item:
            raise TodosError(f"todo {index} : clé 'module' manquante")
        params = item.get("params", {})
        if not isinstance(params, dict):
            raise TodosError(f"todo {index} : 'params' doit être un dict")
        todos.append(Todo(module=item["module"], params=params))

    return todos
