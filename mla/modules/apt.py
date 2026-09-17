"""
Module apt : installe ou désinstalle un paquet APT (idempotent).
"""

import logging
import shlex

from mla.modules.base import BaseModule, ModuleError, ModuleResult
from mla.ssh import run_remote_cmd

logger = logging.getLogger()


class Apt(BaseModule):
    name = "apt"

    def _params(self):
        """
        Retourne (name, state) validés, ou lève ModuleError.
        """
        name = self.params.get("name")
        if not name:
            raise ModuleError("apt : paramètre 'name' manquant")
        state = self.params.get("state", "present")
        if state not in ("present", "absent"):
            raise ModuleError(f"apt : state invalide : {state}")
        return name, state

    def _is_installed(self, ssh_client, pkg):
        cmd = (f"dpkg-query -W -f='${{Status}}' {shlex.quote(pkg)} "
               f"2>/dev/null | grep -q 'ok installed'")
        return run_remote_cmd(cmd, ssh_client).exit_code == 0

    def process(self, ssh_client, dry_run=False, sudo_password=None):
        pkg, state = self._params()
        installed = self._is_installed(ssh_client, pkg)

        need_change = (state == "present" and not installed) \
            or (state == "absent" and installed)
        if not need_change:
            return ModuleResult(changed=False)

        verb = "install" if state == "present" else "remove"

        action = (f"sudo -n env DEBIAN_FRONTEND=noninteractive "
                  f"apt-get {verb} -y {shlex.quote(pkg)}")

        if dry_run:
            logger.info("dry run : %s", action)
            return ModuleResult(changed=True)

        result = run_remote_cmd(action, ssh_client)
        if result.exit_code != 0:
            msg = result.stderr or \
                result.stdout or \
                f"apt a échoué (code {result.exit_code})"
            raise ModuleError(msg)

        return ModuleResult(changed=True)
