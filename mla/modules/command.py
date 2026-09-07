"""
Module command : exécute une commande shell arbitraire
sur l'hôte.
"""

import logging
import shlex

from mla.modules.base import BaseModule, ModuleError, ModuleResult
from mla.ssh import run_remote_cmd

logger = logging.getLogger()


class Command(BaseModule):
    name = "command"

    def _build_command(self):
        """
        Construit la chaîne '<shell> -c <command>' à
        exécuter à distance.
        Lève ModuleError si le paramètre 'command' est absent.
        """
        command = self.params.get("command")
        if not command:
            raise ModuleError("paramètre 'command' requis")
        shell = self.params.get("shell", "/bin/bash")
        return f"{shell} -c {shlex.quote(command)}"

    def process(self, ssh_client, dry_run=False):
        full_cmd = self._build_command()

        if dry_run:
            logger.info("dry run: %s", full_cmd)
            return ModuleResult(changed=False)

        result = run_remote_cmd(full_cmd, ssh_client)

        if result.exit_code != 0:
            message = (result.stderr or
                       result.stdout or
                       f"commande terminée avec le code {result.exit_code}")
            raise ModuleError(message)

        return ModuleResult(changed=True)
