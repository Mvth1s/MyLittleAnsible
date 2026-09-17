"""
Module service : pilote un service systemd
(start/stop/restart/enable/disable).
"""

import logging
import shlex

from mla.modules.base import BaseModule, ModuleError, ModuleResult
from mla.ssh import run_remote_cmd

logger = logging.getLogger()


class Service(BaseModule):
    name = "service"
    STATES = (
        "started",
        "restarted",
        "stopped",
        "enabled",
        "disabled",
    )

    def _params(self):
        svc = self.params.get("name")
        if not svc:
            raise ModuleError(
                "service : paramètre 'name' manquant")
        state = self.params.get("state")
        if state not in self.STATES:
            raise ModuleError(
                f"service : state invalide : {state}")
        return svc, state

    def _is_active(self, ssh_client, svc):
        cmd = f"systemctl is-active {shlex.quote(svc)}"
        return run_remote_cmd(cmd, ssh_client).exit_code == 0

    def _is_enabled(self, ssh_client, svc):
        cmd = f"systemctl is-enabled {shlex.quote(svc)}"
        return run_remote_cmd(cmd, ssh_client).exit_code == 0

    def process(self, ssh_client, dry_run=False, sudo_password=None):
        svc, state = self._params()
        match state:
            case "started":
                verb = "start"
                need_change = not self._is_active(ssh_client, svc)
            case "restarted":
                verb = "restart"
                need_change = True
            case "stopped":
                verb = "stop"
                need_change = self._is_active(ssh_client, svc)
            case "enabled":
                verb = "enable"
                need_change = not self._is_enabled(ssh_client, svc)
            case "disabled":
                verb = "disable"
                need_change = self._is_enabled(ssh_client, svc)

        if not need_change:
            return ModuleResult(changed=False)

        cmd = f"sudo -n systemctl {verb} {shlex.quote(svc)}"

        if dry_run:
            logger.info("dry run : %s", cmd)
            return ModuleResult(changed=True)

        result = run_remote_cmd(cmd, ssh_client)
        if result.exit_code != 0:
            msg = (result.stderr or result.stdout
                   or f"systemctl a échoué (code {result.exit_code})")
            raise ModuleError(msg)
        return ModuleResult(changed=True)
