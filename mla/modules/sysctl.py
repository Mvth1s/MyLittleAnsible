"""
Module sysctl : modifie un paramètre kernel
(runtime + éventuellement permanent).
"""

import shlex

from mla.modules.base import (
    BaseModule,
    ModuleError,
    ModuleResult,
    run_sudo,
)
from mla.ssh import run_remote_cmd

CONF_FILE = "/etc/sysctl.d/99-mla.conf"


class Sysctl(BaseModule):
    name = "sysctl"
    DEFAULTS = {"permanent": False}

    def _params(self):
        attribute = self.params.get("attribute")
        if not attribute:
            raise ModuleError("sysctl: missing 'attribute' parameter")
        if "value" not in self.params:
            raise ModuleError("sysctl: missing 'value' parameter")
        value = str(self.params["value"])
        permanent = self.params.get("permanent", self.DEFAULTS["permanent"])
        return attribute, value, permanent

    def _current_value(self, ssh_client, attribute):
        """
        Valeur runtime actuelle, ou None si l'attribut n'existe pas.
        """
        path = "/proc/sys/" + attribute.replace(".", "/")
        result = run_remote_cmd(f"cat {shlex.quote(path)}", ssh_client)
        if result.exit_code != 0:
            return None
        return result.stdout.strip()

    def _line_persisted(self, ssh_client, line):
        cmd = f"grep -qxF {shlex.quote(line)} {CONF_FILE}"
        return run_remote_cmd(cmd, ssh_client).exit_code == 0

    def process(self, ssh_client, dry_run=False, sudo_password=None):
        attribute, value, permanent = self._params()
        line = f"{attribute} = {value}"

        runtime_ok = self._current_value(ssh_client, attribute) == value
        persist_ok = (not permanent) or self._line_persisted(ssh_client, line)

        if runtime_ok and persist_ok:
            return ModuleResult(changed=False)

        actions = []  # [(commande, libellé pour l'erreur)]
        if not runtime_ok:
            actions.append(
                (f"sysctl -w {shlex.quote(f'{attribute}={value}')}",
                 "sysctl -w"))
        if permanent and not persist_ok:
            actions.append(
                (f"echo {shlex.quote(line)} >> {CONF_FILE}",
                 f"writing {CONF_FILE}"))

        if dry_run:
            return ModuleResult(changed=True,
                                commands=[cmd for cmd, _ in actions])

        if not sudo_password:
            raise ModuleError(
                "sysctl: sudo password required but missing from inventory")

        for cmd, what in actions:
            run_sudo(cmd, ssh_client, sudo_password, what)

        return ModuleResult(changed=True)
