"""
Lecture du playbook (todos.yml) et orchestration des todos.
"""
import logging
from dataclasses import dataclass, field

import yaml

from mla import ssh
from mla.logger import escape_newlines, register_secret, truncate_output
from mla.modules.base import ModuleError

logger = logging.getLogger()


class TodosError(Exception):
    """
    Playbook absent, illisible ou mal formé.
    """


@dataclass
class Todo:
    module: str
    params: dict = field(default_factory=dict)


@dataclass
class HostReport:
    ok: int = 0
    changed: int = 0
    fail: int = 0


def load_todos(path):
    """
    Lit 'path' (YAML) et retourne la liste des Todo.
    Lève TodosError si le fichier est absent, invalide ou mal structuré.
    """
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        raise TodosError(f"playbook not found: {path}") from None
    except yaml.YAMLError as exc:
        raise TodosError(f"invalid playbook YAML: {exc}") from exc

    if not isinstance(data, list):
        raise TodosError("invalid playbook: root must be a list")

    todos = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise TodosError(f"todo {index}: invalid definition")
        if "module" not in item:
            raise TodosError(f"todo {index}: missing 'module' key")
        params = item.get("params", {})
        if not isinstance(params, dict):
            raise TodosError(f"todo {index}: 'params' must be a dict")
        todos.append(Todo(module=item["module"], params=params))

    return todos


def _format_params(params):
    """
    'name=nginx state=present'
    à partir de {'name': 'nginx', 'state': 'present'}.
    """
    parts = []
    for key, value in params.items():
        flat = " ".join(str(value).split())
        parts.append(f"{key}={flat}")
    return " ".join(parts)


def run_todos(todos, hosts, registry=None, dry_run=False):
    """
    Exécute chaque todo sur chaque host et logue au format du sujet.

    Retourne {ip: HostReport}.
    """
    if registry is None:
        raise TodosError("no module registry provided")

    for todo in todos:
        if todo.module not in registry:
            raise TodosError(f"unknown module: {todo.module}")

    for host in hosts:
        register_secret(host.password)

    addresses = [h.address for h in hosts]
    logger.info("processing %d tasks on hosts: %s",
                len(todos), ", ".join(addresses))

    clients = {}
    reports = {h.name: HostReport() for h in hosts}
    usable = []
    for host in hosts:
        try:
            clients[host.name] = ssh.connect(host)
            usable.append(host)
        except ssh.SSHConnectionError as exc:
            logger.error("host=%s connection failed: %s",
                         host.address, truncate_output(str(exc)))
            reports[host.name].fail = len(todos)

    try:
        for i, todo in enumerate(todos, start=1):
            params_str = _format_params(todo.params)
            module_cls = registry[todo.module]

            for host in usable:
                ligne = f"[{i}] host={host.address} op={todo.module}"
                if params_str:
                    ligne += f" {params_str}"
                logger.info(ligne)

            for host in usable:
                module = module_cls(todo.params)
                try:
                    result = module.process(clients[host.name],
                                            dry_run=dry_run,
                                            sudo_password=host.password)
                except ModuleError as exc:
                    error = str(exc)
                except Exception as exc:
                    # bug ou erreur imprévue : la trace n'apparaît qu'en
                    # --debug, le run continue sur les autres tâches
                    logger.debug("host=%s op=%s unexpected error",
                                 host.address, todo.module, exc_info=True)
                    error = f"{type(exc).__name__}: {exc}"
                else:
                    error = None

                if error is not None:
                    logger.info("[%d] host=%s op=%s status=KO", i,
                                host.address, todo.module)
                    logger.error("host=%s %s", host.address,
                                 truncate_output(error))
                    reports[host.name].fail += 1
                else:
                    if dry_run:
                        for command in result.commands:
                            logger.info("host=%s dry run: %s",
                                        host.address,
                                        escape_newlines(command))
                    status = "CHANGED" if result.changed else "OK"
                    logger.info("[%d] host=%s op=%s status=%s", i,
                                host.address, todo.module, status)
                    if result.changed:
                        reports[host.name].changed += 1
                    else:
                        reports[host.name].ok += 1

        logger.info("done processing tasks for hosts: %s",
                    ", ".join(addresses))
        for host in hosts:
            r = reports[host.name]
            logger.info("host=%s ok=%d changed=%d fail=%d",
                        host.address, r.ok, r.changed, r.fail)
    finally:
        for client in clients.values():
            client.close()

    return reports
