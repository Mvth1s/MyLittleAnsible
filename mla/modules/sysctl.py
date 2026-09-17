"""
Module sysctl : modifie un paramètre kernel
(runtime + éventuellement permanent).
"""

import logging
import shlex

from mla.modules.base import BaseModule, ModuleError, ModuleResult
from mla.ssh import run_remote_cmd

logger = logging.getLogger()

CONF_FILE = "/etc/sysctl.d/99-mla.conf"


class Sysctl(BaseModule):
    name = "sysctl"

    def _params(self):
        attribute = self.params.get("attribute")
        if not attribute:
            raise ModuleError("sysctl : paramètre 'attribute' manquant")
        if "value" not in self.params:
            raise ModuleError("sysctl : paramètre 'value' manquant")
        value = str(self.params["value"])
        permanent = self.params.get("permanent", False)
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

        if dry_run:
            logger.info(
                "dry run : %s = %s (permanent=%s)",
                attribute, value, permanent)
            return ModuleResult(changed=True)

        if not sudo_password:
            raise ModuleError(
                "sysctl : mot de passe sudo requis mais absent de l'inventory"
            )
        password = shlex.quote(sudo_password)

        if not runtime_ok:
            action = f"sysctl -w {shlex.quote(f'{attribute}={value}')}"
            cmd = f"printf '%s\\n' {password} | sudo -S {action}"
            result = run_remote_cmd(cmd, ssh_client)
            if result.exit_code != 0:
                msg = (
                    result.stderr or result.stdout or
                    f"sysctl -w a échoué (code {result.exit_code})")
                raise ModuleError(msg)

        if permanent and not persist_ok:
            inner = f"echo {shlex.quote(line)} >> {CONF_FILE}"
            action = "sh -c " + shlex.quote(inner)
            cmd = f"printf '%s\\n' {password} | sudo -S {action}"
            result = run_remote_cmd(cmd, ssh_client)
            if result.exit_code != 0:
                msg = (
                    result.stderr or result.stdout or
                    f"écriture de {CONF_FILE} a échoué "
                    f"(code {result.exit_code})")
                raise ModuleError(msg)

        return ModuleResult(changed=True)
