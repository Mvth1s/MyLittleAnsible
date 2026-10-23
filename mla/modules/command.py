"""
Module command : exécute une commande shell arbitraire
sur l'hôte.
"""

import shlex

from mla.modules.base import BaseModule, ModuleError, ModuleResult
from mla.ssh import run_remote_cmd


class Command(BaseModule):
    """
    Module command : exécute une commande shell arbitraire.
    """
    name = "command"
    DEFAULTS = {"shell": "/bin/bash"}

    def _build_command(self):
        """
        Construit la chaîne '<shell> -c <command>' à
        exécuter à distance.
        Lève ModuleError si le paramètre 'command' est absent.
        """
        command = str(self.params.get("command") or "").strip()
        if not command:
            raise ModuleError("command: missing 'command' parameter")
        shell = self.params.get("shell", self.DEFAULTS["shell"])
        return f"{shell} -c {shlex.quote(command)}"

    def process(self, ssh_client, dry_run=False, sudo_password=None):
        """
        Exécute la commande (toujours CHANGED).
        Lève ModuleError si le code retour est non nul.
        """
        full_cmd = self._build_command()

        if dry_run:
            return ModuleResult(changed=True, commands=[full_cmd])

        result = run_remote_cmd(full_cmd, ssh_client)

        if result.exit_code != 0:
            message = (result.stderr or
                       result.stdout or
                       f"command failed (exit code {result.exit_code})")
            raise ModuleError(message)

        return ModuleResult(changed=True)
