"""
Module Copy : copie un fichier ou dossier local vers l'hôte (idempotent).
"""

import hashlib
import logging
import os
import posixpath
import shlex
import stat
from datetime import datetime

from mla.modules.base import (
    BaseModule,
    ModuleError,
    ModuleResult,
    run_checked,
    sudo_cmd,
    upload,
)
from mla.ssh import run_remote_cmd

logger = logging.getLogger()


def local_mode(path):
    """
    Permissions de 'path' en octal ('0644'), pour 'install -m'.
    """
    return f"{stat.S_IMODE(os.stat(path).st_mode):04o}"


def backup_remote(ssh_client, dest, sudo_password=None):
    """
    Copie 'dest' en 'dest.<horodatage>' s'il existe sur l'hôte.
    """
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    quoted = shlex.quote(dest)
    cmd = (f"if [ -e {quoted} ]; then "
           f"cp -a {quoted} {shlex.quote(f'{dest}.{ts}')}; fi")
    if sudo_password:
        cmd = sudo_cmd(cmd, sudo_password)
    run_checked(cmd, ssh_client, "backup")


class Copy(BaseModule):
    name = "copy"

    def _params(self):
        src = self.params.get("src")
        dest = self.params.get("dest")
        backup = self.params.get("backup", False)
        if not src or not dest:
            raise ModuleError(
                "copy: src and dest are required")
        if not os.path.exists(src):
            raise ModuleError(
                f"copy: src not found: {src}")
        return src, dest, backup

    def _targets(self, src, dest):
        """
        (local_abs, remote_abs)
        pour chaque fichier à copier.
        """
        if os.path.isfile(src):
            return [(src, dest)]
        pairs = []
        for root, _dirs, files in os.walk(src):
            for f in files:
                local = os.path.join(root, f)
                rel = os.path.relpath(local, src)
                remote = posixpath.join(dest, *rel.split(os.sep))
                pairs.append((local, remote))
        return pairs

    @staticmethod
    def _sha256_local(path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _remote_matches(self, ssh_client, local, remote):
        result = run_remote_cmd(
            f"sha256sum {shlex.quote(remote)}",
            ssh_client)
        if result.exit_code != 0:
            return False
        remote_hash = result.stdout.split()[0]
        return remote_hash == self._sha256_local(local)

    def process(self, ssh_client, dry_run=False, sudo_password=None):
        src, dest, backup = self._params()
        targets = self._targets(src, dest)

        changed = any(
            not self._remote_matches(
                ssh_client, local, remote)
            for local, remote in targets
        )
        if not changed:
            return ModuleResult(changed=False)

        if dry_run:
            logger.info(
                "dry run: copy %s to %s (%d file(s))",
                src, dest, len(targets))
            return ModuleResult(changed=True)

        if backup:
            backup_remote(ssh_client, dest, sudo_password)

        files = [(local, remote, local_mode(local))
                 for local, remote in targets]
        upload(ssh_client, files, sudo_password)

        return ModuleResult(changed=True)
