"""
Connexion SSH aux hôtes et exécution de commandes distantes.
"""

import getpass
import os
from dataclasses import dataclass

import paramiko


class SSHConnectionError(Exception):
    """
    Connexion ou authentification SSH impossible.
    """


@dataclass
class CmdResult:
    stdout: str
    stderr: str
    exit_code: int


def _build_connect_kwargs(host):
    """
    Retourne les kwargs de 'SSHClient.connect' selon le mode d'auth
    déduit des champs de 'host' (aucun appel réseau ici - testable seul).
    """
    kwargs = {"username": host.user or getpass.getuser()}
    if host.key_file:
        kwargs["key_filename"] = os.path.expanduser(host.key_file)
    elif host.password:
        kwargs["password"] = host.password
    return kwargs


def connect(host):
    """
    Ouvre une connexion SSH vers 'host'. Lève SSHConnectionError si ça échoue.
    """
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(host.address, port=host.port,
                       **_build_connect_kwargs(host))
    except (paramiko.SSHException, OSError) as exc:
        raise SSHConnectionError(
            f"connexion à {host.address} impossible : {exc}"
        ) from exc
    return client


def run_remote_cmd(command: str, ssh_client: paramiko.SSHClient) -> CmdResult:
    """
    Exécute 'command' sur 'ssh_client' et retourne un CmdResult.
    """
    stdin, stdout, stderr = ssh_client.exec_command(command)
    exit_code = stdout.channel.recv_exit_status()  # bloque jusqu'à la fin
    return CmdResult(
        stdout=stdout.read().decode(), stderr=stderr.read().decode(),
        exit_code=exit_code)
