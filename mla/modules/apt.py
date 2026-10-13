"""
Module apt : installe ou désinstalle un paquet APT (idempotent).
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


class Apt(BaseModule):
    name = "apt"

    def _params(self):
        """
        Retourne (name, state) validés, ou lève ModuleError.
        """
        name = self.params.get("name")
        if not name:
            raise ModuleError("apt: missing 'name' parameter")
        state = self.params.get("state", "present")
        if state not in ("present", "absent"):
            raise ModuleError(f"apt: invalid state: {state}")
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

        quoted = shlex.quote(pkg)
        if state == "present":
            action = ("apt-get update -qq && "
                      "DEBIAN_FRONTEND=noninteractive "
                      f"apt-get install -y {quoted}")
        else:
            action = ("DEBIAN_FRONTEND=noninteractive "
                      f"apt-get remove -y {quoted}")

        if dry_run:
            logger.info("dry run: %s", action)
            return ModuleResult(changed=True)

        if not sudo_password:
            raise ModuleError(
                "apt: sudo password required but missing from inventory")

        run_checked(sudo_cmd(action, sudo_password), ssh_client, "apt")
        return ModuleResult(changed=True)
