"""
Classe de base pour tous les modules (apt, copy, service, ...)
et helpers partagés (sudo, upload).
"""

import io
import logging
import posixpath
import shlex
from dataclasses import dataclass, field

from mla.ssh import run_remote_cmd

logger = logging.getLogger()


class ModuleError(Exception):
    """
    Le module n'a pas pu appliquer son action sur l'hôte.
    """


@dataclass
class ModuleResult:
    changed: bool
    # en dry-run : commandes qui auraient été exécutées (sans mot de passe)
    commands: list[str] = field(default_factory=list)
    # avertissements à loguer par run_todos, préfixés par l'hôte
    warnings: list[str] = field(default_factory=list)


class BaseModule:
    name: str = "anonymous"
    # valeurs des paramètres optionnels, affichées dans l'en-tête de tâche
    DEFAULTS: dict = {}

    def __init__(self, params: dict):
        self.params = params

    def process(self, ssh_client, dry_run=False, sudo_password=None):
        """
        Applique l'action sur 'ssh_client' en utilisant 'self.params'.

        Retourne un ModuleResult, ou lève ModuleError en cas d'échec.
        Les classes filles DOIVENT redéfinir cette méthode.
        """
        raise NotImplementedError


def sudo_cmd(command):
    """
    Enveloppe 'command' dans un unique sudo qui lit le mot de passe sur
    stdin (-S), sans prompt (-p '') pour ne pas polluer la sortie.
    """
    return f"sudo -S -p '' sh -c {shlex.quote(command)}"


def run_checked(command, ssh_client, what, stdin_data=None):
    """
    Exécute 'command' et retourne son CmdResult.
    Lève ModuleError si le code retour est non nul.
    """
    result = run_remote_cmd(command, ssh_client, stdin_data=stdin_data)
    if result.exit_code != 0:
        raise ModuleError(
            result.stderr.strip() or result.stdout.strip()
            or f"{what} failed (exit code {result.exit_code})")
    return result


def run_sudo(command, ssh_client, password, what):
    """
    Exécute 'command' via sudo, mot de passe envoyé sur stdin (jamais
    dans la ligne de commande, donc invisible dans 'ps' sur l'hôte).
    """
    return run_checked(sudo_cmd(command), ssh_client, what,
                       stdin_data=f"{password}\n")


def _put(sftp, source, remote):
    """
    Envoie 'source' (chemin local ou bytes) vers 'remote'.
    """
    if isinstance(source, bytes):
        sftp.putfo(io.BytesIO(source), remote)
    else:
        sftp.put(source, remote)


def upload_commands(files, sudo_password=None):
    """
    Décrit ce que ferait 'upload' pour 'files' = [(local, remote, mode)],
    pour le dry-run (le dossier temporaire n'existe pas encore : on
    affiche le fichier local à sa place).
    """
    commands = []
    for local, remote, mode in files:
        quoted = shlex.quote(remote)
        if sudo_password:
            commands.append(
                f"install -D -m {mode} {shlex.quote(local)} {quoted}")
        else:
            parent = shlex.quote(posixpath.dirname(remote))
            commands.append(f"mkdir -p {parent}")
            commands.append(f"sftp put {shlex.quote(local)} {quoted}")
    return commands


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
        run_sudo(" && ".join(installs), ssh_client, sudo_password,
                 "install")
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
