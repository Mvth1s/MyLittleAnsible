# MyLittleAnsible

Groupe 1078234 — `aguado_m`, `moulou_h`
Dépôt : <https://rendu-git.etna-alternance.net/module-10353/activity-55555/group-1078234>

Outil en ligne de commande pour configurer des hôtes distants via SSH à partir
de fichiers YAML déclaratifs, dans l'esprit d'Ansible. On décrit l'état voulu
(paquets, services, fichiers, paramètres kernel…) dans un *playbook* `todos.yml`,
la liste des cibles dans un `inventory.yml`, et `mla` applique.

Statut : **en cours de développement**.

## Prérequis

- Python 3.11+ (l'environnement de correction est Debian 12 « bookworm »)
- Un accès SSH aux hôtes cibles

## Installation

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .            # expose la commande `mla`
```

Dépendances de développement (lint + tests) : `pip install -r requirements-dev.txt`.

## Utilisation

```sh
mla -f todos.yml -i inventory.yml
```

| Flag        | Rôle                                                             |
|-------------|-----------------------------------------------------------------|
| `-f`        | fichier des todos (playbook) à exécuter                          |
| `-i`        | fichier d'inventory décrivant les hôtes cibles                   |
| `--debug`   | affiche les stack traces en cas d'erreur (masquées par défaut)   |
| `--dry-run` | n'applique rien : affiche seulement les commandes qui seraient exécutées |

Exemple de sortie :

```
2022-01-06 21:49:16,432 - root - INFO - processing 6 tasks on hosts: 192.168.1.22, 192.168.1.24
2022-01-06 21:49:16,432 - root - INFO - [1] host=192.168.1.22 op=apt name=nginx-common state=present
2022-01-06 21:49:16,432 - root - INFO - [1] host=192.168.1.22 op=apt status=OK
...
2022-01-06 21:49:16,432 - root - INFO - host=192.168.1.22 ok=1 changed=5 fail=0
```

## Inventory

```yaml
hosts:
  webserver:
    ssh_address: 192.168.1.22
    ssh_port: 2222
  bastion:
    ssh_address: 192.168.1.24
    ssh_port: 22
```

### Authentification SSH

Trois modes, choisis par hôte via des attributs supplémentaires dans l'inventory :

| Mode                      | Attributs                       | Équivalent `ssh`              |
|---------------------------|---------------------------------|------------------------------|
| Configuration par défaut  | *(aucun)*                       | `ssh <host>` (fichiers `~/.ssh/`) |
| Utilisateur / mot de passe| `ssh_user`, `ssh_password`      | `ssh user@host`              |
| Clé privée                | `ssh_user`, `ssh_key_file`      | `ssh -i key.pem user@host`   |

## Todos (playbook)

```yaml
- module: apt
  params:
    name: nginx-common
    state: present

- module: copy
  params:
    src: ./public
    dest: /var/www/public
    backup: true

- module: service
  params:
    name: nginx
    state: started
```

### Modules disponibles

| Module     | Rôle                                              | Paramètres principaux                     |
|------------|--------------------------------------------------|------------------------------------------|
| `apt`      | installe / désinstalle des paquets APT           | `name`, `state` (`present` / `absent`)   |
| `copy`     | copie un fichier ou dossier local vers la cible  | `src`, `dest`, `backup`                  |
| `template` | rend un template Jinja2 sur la cible             | `src`, `dest`, `vars`                    |
| `service`  | pilote un service systemd                        | `name`, `state` (`started`, `restarted`, `stopped`, `enabled`, `disabled`) |
| `sysctl`   | modifie un paramètre kernel                      | `attribute`, `value`, `permanent`       |
| `command`  | exécute une commande shell arbitraire            | `command`, `shell`                      |

## Développement

Structure du paquet :

```
mla/
├── cli.py          point d'entrée CLI (parsing des flags)
├── inventory.py    lecture / validation de l'inventory
├── todos.py        lecture du playbook et orchestration
├── ssh.py          connexions SSH et exécution de commandes distantes
├── logger.py       configuration du logging
└── modules/        un module par action (base.py = classe parente)
tests/              un fichier de tests par module (+ fixtures/ pour les YAML de test)
```

Installer les outils de dev : `pip install -r requirements-dev.txt`.

Lancer le style et les tests :

```sh
.venv/bin/pycodestyle mla/ tests/
.venv/bin/pytest -q
```

`pyproject.toml` configure `pytest` (`pythonpath = ["."]`) pour que les fichiers
de `tests/` puissent faire `from mla... import ...` quel que soit le dossier
depuis lequel `pytest` est lancé.

Le code doit respecter la PEP8 ; `print` est interdit, tout passe par `logging`.

## Environnement de test local

Deux conteneurs Debian + systemd + sshd pour tester les trois modes d'auth et
l'idempotence, sans machines distantes. Voir [`docker/README.md`](docker/README.md).
Ce dossier ne fait pas partie du rendu.
