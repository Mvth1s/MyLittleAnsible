"""
Module sysctl : modifie un paramètre kernel
(runtime + éventuellement permanent).
"""

import logging
import shlex

from mla.modules.base import (
    BaseModule,
    ModuleError,
    ModuleResult,
    run_checked,
    sudo_cmd,
)
from mla.ssh import run_remote_cmd

logger = logging.getLogger()

CONF_FILE = "/etc/sysctl.d/99-mla.conf"


class Sysctl(BaseModule):
    name = "sysctl"

    def _params(self):
        attribute = self.params.get("attribute")
        if not attribute:
            raise ModuleError("sysctl: missing 'attribute' parameter")
        if "value" not in self.params:
            raise ModuleError("sysctl: missing 'value' parameter")
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
                "dry run: %s = %s (permanent=%s)",
                attribute, value, permanent)
            return ModuleResult(changed=True)

        if not sudo_password:
            raise ModuleError(
                "sysctl: sudo password required but missing from inventory")

        if not runtime_ok:
            action = f"sysctl -w {shlex.quote(f'{attribute}={value}')}"
            run_checked(sudo_cmd(action, sudo_password), ssh_client,
                        "sysctl -w")

        if permanent and not persist_ok:
            action = f"echo {shlex.quote(line)} >> {CONF_FILE}"
            run_checked(sudo_cmd(action, sudo_password), ssh_client,
                        f"writing {CONF_FILE}")

        return ModuleResult(changed=True)
