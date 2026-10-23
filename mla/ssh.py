"""
Connexion SSH aux hôtes et exécution de commandes distantes.
"""

import getpass
import os
from dataclasses import dataclass

import paramiko


# secondes : connexion TCP, bannière SSH, authentification
CONNECT_TIMEOUT = 10
DEFAULT_PORT = 22
SSH_CONFIG = "~/.ssh/config"


class SSHConnectionError(Exception):
    """
    Connexion ou authentification SSH impossible.
    """


@dataclass
class CmdResult:
    """
    Sortie standard, sortie d'erreur et code retour d'une commande distante.
    """
    stdout: str
    stderr: str
    exit_code: int


def load_ssh_config(address):
    """
    Options de ~/.ssh/config applicables à 'address' (clés en minuscules,
    comme 'ssh <address>' les verrait). {} si le fichier n'existe pas.
    """
    path = os.path.expanduser(SSH_CONFIG)
    if not os.path.isfile(path):
        return {}
    return paramiko.SSHConfig.from_path(path).lookup(address)


def _build_connect_kwargs(host, config=None):
    """
    Retourne les kwargs de 'SSHClient.connect' selon le mode d'auth
    déduit des champs de 'host', complétés par 'config' (options de
    ~/.ssh/config) quand l'inventory ne précise rien. Aucun appel réseau
    ni lecture de fichier ici - testable seul.
    """
    config = config or {}
    kwargs = {"username": host.user or config.get("user")
              or getpass.getuser()}
    if host.password:
        # avec une clé, paramiko essaie la clé puis se replie dessus
        kwargs["password"] = host.password
    if host.key_file:
        kwargs["key_filename"] = os.path.expanduser(host.key_file)
    elif not host.password and config.get("identityfile"):
        kwargs["key_filename"] = os.path.expanduser(
            config["identityfile"][0])
    return kwargs


def _resolve_target(host, config):
    """
    (adresse, port) effectifs : 'HostName' de ~/.ssh/config s'il existe,
    port de l'inventory > port de ~/.ssh/config > 22.
    """
    address = config.get("hostname", host.address)
    if host.port is not None:
        port = host.port
    else:
        port = int(config.get("port", DEFAULT_PORT))
    return address, port


def connect(host):
    """
    Ouvre une connexion SSH vers 'host', comme 'ssh' le ferait avec
    ~/.ssh/config. Lève SSHConnectionError si ça échoue.
    """
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        config = load_ssh_config(host.address)
        address, port = _resolve_target(host, config)
        client.connect(address, port=port,
                       **_build_connect_kwargs(host, config),
                       timeout=CONNECT_TIMEOUT,
                       banner_timeout=CONNECT_TIMEOUT,
                       auth_timeout=CONNECT_TIMEOUT)
    except (paramiko.SSHException, OSError, ValueError) as exc:
        raise SSHConnectionError(str(exc) or type(exc).__name__) from exc
    return client


def run_remote_cmd(command: str, ssh_client: paramiko.SSHClient,
                   stdin_data: str | None = None) -> CmdResult:
    """
    Exécute 'command' sur 'ssh_client' et retourne un CmdResult.
    'stdin_data' (ex. mot de passe sudo) est écrit sur l'entrée standard
    du canal puis fermé : il n'apparaît jamais dans la ligne de commande.
    """
    stdin, stdout, stderr = ssh_client.exec_command(command)
    if stdin_data is not None:
        stdin.write(stdin_data)
        stdin.flush()
        stdin.channel.shutdown_write()
    exit_code = stdout.channel.recv_exit_status()  # bloque jusqu'à la fin
    return CmdResult(
        stdout=stdout.read().decode(), stderr=stderr.read().decode(),
        exit_code=exit_code)
