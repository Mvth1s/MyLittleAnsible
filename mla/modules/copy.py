"""
Module Copy : copie un fichier ou dossier local vers l'hôte (idempotent).
"""

import hashlib
import logging
import os
import posixpath
import shlex
from datetime import datetime

from mla.modules.base import BaseModule, ModuleError, ModuleResult
from mla.ssh import run_remote_cmd

logger = logging.getLogger()


class Copy(BaseModule):
    name = "copy"

    def _params(self):
        src = self.params.get("src")
        dest = self.params.get("dest")
        backup = self.params.get("backup", False)
        if not src or not dest:
            raise ModuleError(
                "copy : src et dest sont obligatoires")
        if not os.path.exists(src):
            raise ModuleError(
                f"copy : src introuvable : {src}")
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
                remote = posixpath.join(dest, rel)
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
                "dry_run : copie de %s vers %s (%d fichier(s))",
                src, dest, len(targets))
            return ModuleResult(changed=True)

        if backup:
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            run_remote_cmd(
                f"test -e {shlex.quote(dest)} && "
                f"cp -a {shlex.quote(dest)} "
                f"{shlex.quote(dest + '.' + ts)}",
                ssh_client,
            )

        sftp = ssh_client.open_sftp()
        for local, remote in targets:
            parent = os.path.dirname(remote)
            run_remote_cmd(
                f"mkdir -p {shlex.quote(parent)}",
                ssh_client)
            sftp.put(local, remote)

        return ModuleResult(changed=True)
