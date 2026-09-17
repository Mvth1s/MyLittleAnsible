"""
Point d'entrée en ligne de commande :
    `mla -f todos.yml -i inventory.yml`
"""

import sys
import warnings

import click
from cryptography.utils import CryptographyDeprecationWarning

warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)

from mla.inventory import load_inventory
from mla.logger import configure_logging
from mla.modules import MODULES
from mla.todos import load_todos, run_todos


@click.command()
@click.option("-f", "todos_path", required=True,
              help="fichier YAML des todos (playbook)")
@click.option("-i", "inventory_path", required=True,
              help="fichier YAML d'inventory")
@click.option("--debug", is_flag=True,
              help="affiche les stack traces en cas d'erreur")
@click.option("--dry-run", is_flag=True,
              help="n'applique rien, affiche seulement les commandes")
def main(todos_path, inventory_path, debug, dry_run):
    """
    MyLittleAnsible : applique un playbook YAML
    sur des hôtes distants.
    """
    configure_logging(debug=debug)

    hosts = load_inventory(inventory_path)
    todos = load_todos(todos_path)
    reports = run_todos(todos, hosts, registry=MODULES,
                        dry_run=dry_run)

    if any(r.fail > 0 for r in reports.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
