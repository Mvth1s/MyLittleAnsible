"""
Module apt : installe ou désinstalle un paquet APT (idempotent).
"""

import shlex

from mla.modules.base import (
    BaseModule,
    ModuleError,
    ModuleResult,
    run_sudo,
)
from mla.ssh import run_remote_cmd


class Apt(BaseModule):
    """
    Module apt : installe (present) ou désinstalle (absent) un paquet.
    """
    name = "apt"
    DEFAULTS = {"state": "present"}

    def _params(self):
        """
        Retourne (name, state) validés, ou lève ModuleError.
        """
        name = self.params.get("name")
        if not name:
            raise ModuleError("apt: missing 'name' parameter")
        state = self.params.get("state", self.DEFAULTS["state"])
        if state not in ("present", "absent"):
            raise ModuleError(f"apt: invalid state: {state}")
        return name, state

    def _is_installed(self, ssh_client, pkg):
        """
        True si le paquet 'pkg' est installé sur l'hôte.
        """
        cmd = (f"dpkg-query -W -f='${{Status}}' {shlex.quote(pkg)} "
               f"2>/dev/null | grep -q 'ok installed'")
        return run_remote_cmd(cmd, ssh_client).exit_code == 0

    def process(self, ssh_client, dry_run=False, sudo_password=None):
        """
        Installe ou désinstalle le paquet si son état diffère de 'state'.
        """
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
            return ModuleResult(changed=True, commands=[action])

        if not sudo_password:
            raise ModuleError(
                "apt: sudo password required but missing from inventory")

        run_sudo(action, ssh_client, sudo_password, "apt")
        return ModuleResult(changed=True)
