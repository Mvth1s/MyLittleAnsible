"""
Classe de base pour tous les modules (apt, copy, service, ...)
et helpers partagés (sudo, upload).
"""

import io
import logging
import posixpath
import shlex
from dataclasses import dataclass

from mla.ssh import run_remote_cmd

logger = logging.getLogger()


class ModuleError(Exception):
    """
    Le module n'a pas pu appliquer son action sur l'hôte.
    """


@dataclass
class ModuleResult:
    changed: bool


class BaseModule:
    name: str = "anonymous"

    def __init__(self, params: dict):
        self.params = params

    def process(self, ssh_client, dry_run=False, sudo_password=None):
        """
        Applique l'action sur 'ssh_client' en utilisant 'self.params'.

        Retourne un ModuleResult, ou lève ModuleError en cas d'échec.
        Les classes filles DOIVENT redéfinir cette méthode.
        """
        raise NotImplementedError


def sudo_cmd(command, password):
    """
    Enveloppe 'command' dans un unique sudo alimenté par 'password'
    sur stdin, sans prompt (-p '') pour ne pas polluer la sortie.
    """
    return (f"printf '%s\\n' {shlex.quote(password)} | "
            f"sudo -S -p '' sh -c {shlex.quote(command)}")


def run_checked(command, ssh_client, what):
    """
    Exécute 'command' et retourne son CmdResult.
    Lève ModuleError si le code retour est non nul.
    """
    result = run_remote_cmd(command, ssh_client)
    if result.exit_code != 0:
        raise ModuleError(
            result.stderr.strip() or result.stdout.strip()
            or f"{what} failed (exit code {result.exit_code})")
    return result


def _put(sftp, source, remote):
    """
    Envoie 'source' (chemin local ou bytes) vers 'remote'.
    """
    if isinstance(source, bytes):
        sftp.putfo(io.BytesIO(source), remote)
    else:
        sftp.put(source, remote)


def upload(ssh_client, files, sudo_password=None):
    """
    Pousse 'files' = [(source, remote, mode), ...] sur l'hôte.

    'source' est un chemin local ou des bytes, 'mode' une chaîne
    octale ('0644').
    Avec 'sudo_password' : dépôt dans un dossier temporaire puis un seul
    sudo 'install -D' pour tout placer.
    Sans : mkdir -p du parent puis envoi direct par SFTP.
    """
    if not sudo_password:
        with ssh_client.open_sftp() as sftp:
            for source, remote, _mode in files:
                parent = posixpath.dirname(remote)
                run_checked(f"mkdir -p {shlex.quote(parent)}",
                            ssh_client, "mkdir")
                _put(sftp, source, remote)
        return

    tmpdir = run_checked("mktemp -d", ssh_client, "mktemp").stdout.strip()
    done = False
    try:
        installs = []
        with ssh_client.open_sftp() as sftp:
            for index, (source, remote, mode) in enumerate(files):
                staged = posixpath.join(tmpdir, str(index))
                _put(sftp, source, staged)
                installs.append(
                    f"install -D -m {mode} {shlex.quote(staged)} "
                    f"{shlex.quote(remote)}")
        run_checked(sudo_cmd(" && ".join(installs), sudo_password),
                    ssh_client, "install")
        done = True
    finally:
        cleanup = run_remote_cmd(f"rm -rf {shlex.quote(tmpdir)}", ssh_client)
        if cleanup.exit_code != 0:
            # ne pas masquer une erreur déjà en cours de propagation
            if done:
                raise ModuleError(
                    f"cleanup of {tmpdir} failed "
                    f"(exit code {cleanup.exit_code})")
            logger.warning("cleanup of %s failed (exit code %d)",
                           tmpdir, cleanup.exit_code)
