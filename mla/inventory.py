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
    port: int = 22
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
        raise InventoryError(f"inventory introuvable : {path}") from None
    except yaml.YAMLError as exc:
        raise InventoryError(f"inventory YAML invalide : {exc}") from exc

    # B. valider la structure
    if not isinstance(data, dict) or "hosts" not in data:
        raise InventoryError("inventory invalide : clé 'hosts' absente")
    if not isinstance(data["hosts"], dict):
        raise InventoryError("inventory invalide : 'hosts' doit être un dict")

    # C. construire les Host
    hosts = []
    for name, params in data["hosts"].items():
        if not isinstance(params, dict):
            raise InventoryError(f"host {name} : définition invalide")
        if "ssh_address" not in params:
            raise InventoryError(f"host {name} : ssh_address manquant")
        hosts.append(Host(
            name=name,
            address=params["ssh_address"],
            port=params.get("ssh_port", 22),
            user=params.get("ssh_user"),
            password=params.get("ssh_password"),
            key_file=params.get("ssh_key_file"),
        ))

    return hosts
