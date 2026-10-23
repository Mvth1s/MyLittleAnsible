"""
Lecture et validation du fichier d'inventory.
"""

from dataclasses import dataclass
import yaml


class InventoryError(Exception):
    """
    Inventory absent, illisible ou mal formé.
    """


@dataclass
class Host:
    name: str
    address: str
    # None : ~/.ssh/config, puis 22, décident à la connexion
    port: int | None = None
    user: str | None = None
    password: str | None = None
    key_file: str | None = None


def load_inventory(path):
    """
    Lit 'path' (YAML) et retourne la liste des Hosts.
    Lève InventoryError si le fichier est absent, invalide ou mal structuré.
    """
    # A. lire le fichier
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        raise InventoryError(f"inventory not found: {path}") from None
    except yaml.YAMLError as exc:
        raise InventoryError(f"invalid inventory YAML: {exc}") from exc

    # B. valider la structure
    if not isinstance(data, dict) or "hosts" not in data:
        raise InventoryError("invalid inventory: missing 'hosts' key")
    if not isinstance(data["hosts"], dict):
        raise InventoryError("invalid inventory: 'hosts' must be a dict")

    # C. construire les Host
    hosts = []
    for name, params in data["hosts"].items():
        if not isinstance(params, dict):
            raise InventoryError(f"host {name}: invalid definition")
        if "ssh_address" not in params:
            raise InventoryError(f"host {name}: missing ssh_address")
        hosts.append(Host(
            name=name,
            address=params["ssh_address"],
            port=params.get("ssh_port"),
            user=params.get("ssh_user"),
            password=params.get("ssh_password"),
            key_file=params.get("ssh_key_file"),
        ))

    return hosts
