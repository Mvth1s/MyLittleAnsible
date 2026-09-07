"""
Classe de base pour tous les modules (apt, copy, service, ...).
"""

from dataclasses import dataclass


class ModuleError(Exception):
    """
    Le module n'a pas pu appliquer son action sur l'hôte.
    """


@dataclass
class ModuleResult:
    changed: bool


class BaseModule:
    name: str = "anonymous"

    def __init__(self, params: dict):
        self.params = params

    def process(self, ssh_client, dry_run=False):
        """
        Applique l'action sur 'ssh_client' en utilisant 'self.params'.

        Retourne un ModuleResult, ou lève ModuleError en cas d'échec.
        Les classes filles DOIVENT redéfinir cette méthode.
        """
        raise NotImplementedError
