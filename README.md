# MyLittleAnsible

Groupe 1078234 — `aguado_m`, `moulou_h`
Dépôt : <https://rendu-git.etna-alternance.net/module-10353/activity-55555/group-1078234>

Outil en ligne de commande pour configurer des hôtes distants via SSH à partir
de fichiers YAML déclaratifs, dans l'esprit d'Ansible. On décrit l'état voulu
(paquets, services, fichiers, paramètres kernel…) dans un *playbook* `todos.yml`,
la liste des cibles dans un `inventory.yml`, et `mla` applique.

Statut : **terminé**.

- [x] `logger.py` — logging (format, `--debug`, préfixe host, troncature erreurs)
- [x] `inventory.py` — lecture/validation de l'inventory YAML
- [x] `ssh.py` — connexion SSH (3 modes d'auth) + exécution de commande distante
- [x] `modules/base.py` — classe parente commune (`BaseModule`, `ModuleResult`, `ModuleError`)
- [x] `modules/` — `command`, `apt`, `copy`, `service`, `sysctl`, `template`
- [x] `todos.py` — lecture du playbook (`load_todos`) + orchestration (`run_todos`)
- [x] `cli.py` — point d'entrée (`-f`, `-i`, `--debug`, `--dry-run`)

## Prérequis

- Python 3.11+ (l'environnement de correction est Debian 12 « bookworm »)
- Un accès SSH aux hôtes cibles

## Installation

```sh
python -m venv .venv
source .venv/bin/activate          # bash / zsh
source .venv/bin/activate.fish     # fish
pip install -r requirements.txt
pip install -e .                   # expose la commande `mla`
```

Dépendances de développement (lint + tests) : `pip install -r requirements-dev.txt`,
puis `python -m pytest -q` et `python -m pycodestyle mla/ tests/`.

## Démo rapide (conteneurs Docker)

Le dossier [`docker/`](docker/README.md) fournit deux hôtes Debian 12 jetables
(`172.28.0.11` et `172.28.0.12`). Une fois la clé de test générée (voir
[`docker/README.md`](docker/README.md), étape 1), depuis la racine du dépôt :

```sh
cp inventory.example.yml inventory.yml
cd docker && docker compose up -d && cd ..
mla -f todos-full.yml -i inventory.yml
```

`todos-full.yml` utilise les six modules : installe nginx, copie `./public`,
pousse un vhost Jinja2 (`default.conf.j2`), redémarre et active nginx, règle
`net.core.somaxconn` de façon permanente, puis lance une commande shell.

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

Exemple réel : `todos-full.yml` sur les deux conteneurs fraîchement recréés.

Premier passage, tout est à appliquer :

```
2026-10-13 13:25:59,050 - root - INFO - processing 7 tasks on hosts: 172.28.0.11, 172.28.0.12
2026-10-13 13:25:59,194 - root - INFO - [1] host=172.28.0.11 op=apt name=nginx state=present
2026-10-13 13:25:59,194 - root - INFO - [1] host=172.28.0.12 op=apt name=nginx state=present
2026-10-13 13:26:00,988 - root - INFO - [1] host=172.28.0.11 op=apt status=CHANGED
2026-10-13 13:26:02,787 - root - INFO - [1] host=172.28.0.12 op=apt status=CHANGED
2026-10-13 13:26:02,787 - root - INFO - [2] host=172.28.0.11 op=copy src=./public dest=/var/www/public backup=True
2026-10-13 13:26:02,787 - root - INFO - [2] host=172.28.0.12 op=copy src=./public dest=/var/www/public backup=True
2026-10-13 13:26:03,002 - root - INFO - [2] host=172.28.0.11 op=copy status=CHANGED
2026-10-13 13:26:03,218 - root - INFO - [2] host=172.28.0.12 op=copy status=CHANGED
2026-10-13 13:26:03,218 - root - INFO - [3] host=172.28.0.11 op=template src=default.conf.j2 dest=/etc/nginx/sites-enabled/default vars={'listen_port': 8000, 'server_name': '_'}
2026-10-13 13:26:03,218 - root - INFO - [3] host=172.28.0.12 op=template src=default.conf.j2 dest=/etc/nginx/sites-enabled/default vars={'listen_port': 8000, 'server_name': '_'}
2026-10-13 13:26:03,374 - root - INFO - [3] host=172.28.0.11 op=template status=CHANGED
2026-10-13 13:26:03,528 - root - INFO - [3] host=172.28.0.12 op=template status=CHANGED
2026-10-13 13:26:03,528 - root - INFO - [4] host=172.28.0.11 op=service name=nginx state=restarted
2026-10-13 13:26:03,528 - root - INFO - [4] host=172.28.0.12 op=service name=nginx state=restarted
2026-10-13 13:26:03,571 - root - INFO - [4] host=172.28.0.11 op=service status=CHANGED
2026-10-13 13:26:03,610 - root - INFO - [4] host=172.28.0.12 op=service status=CHANGED
2026-10-13 13:26:03,610 - root - INFO - [5] host=172.28.0.11 op=service name=nginx state=enabled
2026-10-13 13:26:03,610 - root - INFO - [5] host=172.28.0.12 op=service name=nginx state=enabled
2026-10-13 13:26:03,616 - root - INFO - [5] host=172.28.0.11 op=service status=OK
2026-10-13 13:26:03,656 - root - INFO - [5] host=172.28.0.12 op=service status=OK
2026-10-13 13:26:03,656 - root - INFO - [6] host=172.28.0.11 op=sysctl attribute=net.core.somaxconn value=8192 permanent=True
2026-10-13 13:26:03,656 - root - INFO - [6] host=172.28.0.12 op=sysctl attribute=net.core.somaxconn value=8192 permanent=True
2026-10-13 13:26:03,825 - root - INFO - [6] host=172.28.0.11 op=sysctl status=CHANGED
2026-10-13 13:26:03,993 - root - INFO - [6] host=172.28.0.12 op=sysctl status=CHANGED
2026-10-13 13:26:03,993 - root - INFO - [7] host=172.28.0.11 op=command command=echo "test" > /tmp/dummy-file cat /tmp/dummy-file
2026-10-13 13:26:03,993 - root - INFO - [7] host=172.28.0.12 op=command command=echo "test" > /tmp/dummy-file cat /tmp/dummy-file
2026-10-13 13:26:03,996 - root - INFO - [7] host=172.28.0.11 op=command status=CHANGED
2026-10-13 13:26:04,037 - root - INFO - [7] host=172.28.0.12 op=command status=CHANGED
2026-10-13 13:26:04,037 - root - INFO - done processing tasks for hosts: 172.28.0.11, 172.28.0.12
2026-10-13 13:26:04,037 - root - INFO - host=172.28.0.11 ok=1 changed=6 fail=0
2026-10-13 13:26:04,037 - root - INFO - host=172.28.0.12 ok=1 changed=6 fail=0
```

Second passage, idempotent : seuls `service state=restarted` et `command` restent
`CHANGED`, par construction (voir [Comportements à connaître](#comportements-à-connaître)).
`service state=enabled` est déjà `OK` au premier passage car le paquet nginx
active lui-même le service à l'installation.

```
2026-10-13 13:26:04,129 - root - INFO - processing 7 tasks on hosts: 172.28.0.11, 172.28.0.12
2026-10-13 13:26:04,274 - root - INFO - [1] host=172.28.0.11 op=apt name=nginx state=present
2026-10-13 13:26:04,274 - root - INFO - [1] host=172.28.0.12 op=apt name=nginx state=present
2026-10-13 13:26:04,278 - root - INFO - [1] host=172.28.0.11 op=apt status=OK
2026-10-13 13:26:04,323 - root - INFO - [1] host=172.28.0.12 op=apt status=OK
2026-10-13 13:26:04,323 - root - INFO - [2] host=172.28.0.11 op=copy src=./public dest=/var/www/public backup=True
2026-10-13 13:26:04,323 - root - INFO - [2] host=172.28.0.12 op=copy src=./public dest=/var/www/public backup=True
2026-10-13 13:26:04,325 - root - INFO - [2] host=172.28.0.11 op=copy status=OK
2026-10-13 13:26:04,367 - root - INFO - [2] host=172.28.0.12 op=copy status=OK
2026-10-13 13:26:04,367 - root - INFO - [3] host=172.28.0.11 op=template src=default.conf.j2 dest=/etc/nginx/sites-enabled/default vars={'listen_port': 8000, 'server_name': '_'}
2026-10-13 13:26:04,367 - root - INFO - [3] host=172.28.0.12 op=template src=default.conf.j2 dest=/etc/nginx/sites-enabled/default vars={'listen_port': 8000, 'server_name': '_'}
2026-10-13 13:26:04,371 - root - INFO - [3] host=172.28.0.11 op=template status=OK
2026-10-13 13:26:04,411 - root - INFO - [3] host=172.28.0.12 op=template status=OK
2026-10-13 13:26:04,411 - root - INFO - [4] host=172.28.0.11 op=service name=nginx state=restarted
2026-10-13 13:26:04,411 - root - INFO - [4] host=172.28.0.12 op=service name=nginx state=restarted
2026-10-13 13:26:04,473 - root - INFO - [4] host=172.28.0.11 op=service status=CHANGED
2026-10-13 13:26:04,534 - root - INFO - [4] host=172.28.0.12 op=service status=CHANGED
2026-10-13 13:26:04,534 - root - INFO - [5] host=172.28.0.11 op=service name=nginx state=enabled
2026-10-13 13:26:04,534 - root - INFO - [5] host=172.28.0.12 op=service name=nginx state=enabled
2026-10-13 13:26:04,538 - root - INFO - [5] host=172.28.0.11 op=service status=OK
2026-10-13 13:26:04,579 - root - INFO - [5] host=172.28.0.12 op=service status=OK
2026-10-13 13:26:04,579 - root - INFO - [6] host=172.28.0.11 op=sysctl attribute=net.core.somaxconn value=8192 permanent=True
2026-10-13 13:26:04,579 - root - INFO - [6] host=172.28.0.12 op=sysctl attribute=net.core.somaxconn value=8192 permanent=True
2026-10-13 13:26:04,624 - root - INFO - [6] host=172.28.0.11 op=sysctl status=OK
2026-10-13 13:26:04,668 - root - INFO - [6] host=172.28.0.12 op=sysctl status=OK
2026-10-13 13:26:04,668 - root - INFO - [7] host=172.28.0.11 op=command command=echo "test" > /tmp/dummy-file cat /tmp/dummy-file
2026-10-13 13:26:04,668 - root - INFO - [7] host=172.28.0.12 op=command command=echo "test" > /tmp/dummy-file cat /tmp/dummy-file
2026-10-13 13:26:04,671 - root - INFO - [7] host=172.28.0.11 op=command status=CHANGED
2026-10-13 13:26:04,712 - root - INFO - [7] host=172.28.0.12 op=command status=CHANGED
2026-10-13 13:26:04,712 - root - INFO - done processing tasks for hosts: 172.28.0.11, 172.28.0.12
2026-10-13 13:26:04,712 - root - INFO - host=172.28.0.11 ok=5 changed=2 fail=0
2026-10-13 13:26:04,712 - root - INFO - host=172.28.0.12 ok=5 changed=2 fail=0
```

`mla` sort avec un code non nul dès qu'un hôte a au moins un `fail`.

### Comportements à connaître

- **Logs sur la sortie standard** : tout passe par `logging`, sur stdout (y compris
  les lignes de `--dry-run` et les stack traces de `--debug`). Chaque ligne de log
  tient sur une ligne : les sorties d'erreur multi-lignes (stderr de `systemctl`…)
  sont jointes par ` | ` et tronquées à 200 caractères.
- **Mot de passe masqué** : la valeur de `ssh_password` n'apparaît jamais dans les
  logs, même avec `--debug` (remplacée par `********`).
- **`--dry-run`** : rien n'est modifié sur les hôtes (seules des lectures sont
  faites pour savoir s'il y a un changement). Chaque commande qui serait exécutée
  est loguée, sans le mot de passe ni l'enveloppe `sudo`, au format :

  ```
  host=<ip> dry run: <commande>
  ```

  Les retours à la ligne d'une commande y sont écrits `\n` (backslash + n), par
  exemple :

  ```
  host=172.28.0.11 dry run: systemctl restart nginx
  host=172.28.0.11 dry run: /bin/bash -c 'echo "test" > /tmp/dummy-file\ncat /tmp/dummy-file'
  ```

  Pour `copy` et `template`, le fichier local est affiché à la place du dossier
  temporaire distant (`install -D -m 0644 ./public/index.html /var/www/public/index.html`).
- **Chemins `src` relatifs** (`copy`, `template`) : résolus depuis le dossier
  courant au lancement de `mla`, pas depuis l'emplacement du playbook.
- **`sysctl` avec `permanent: true`** : la ligne `attribut = valeur` est ajoutée
  dans `/etc/sysctl.d/99-mla.conf` sur la cible, en plus de la valeur runtime.
- **Toujours `CHANGED`** : `service` avec `state: restarted` et `command` ne
  peuvent pas savoir si l'état voulu est déjà atteint ; ils s'exécutent et
  renvoient `CHANGED` à chaque passage.

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

| Hôte        | `ssh_address`  | `ssh_port` |
|-------------|----------------|------------|
| `webserver` | `192.168.1.22` | `2222`     |
| `bastion`   | `192.168.1.24` | `22`       |

`ssh_address` est obligatoire, `ssh_port` vaut `22` par défaut. Le YAML fait foi :
le texte du sujet inverse les deux ports dans sa description de cet exemple.

### Authentification SSH

Trois modes, choisis par hôte via des attributs supplémentaires dans l'inventory :

| Mode                      | Attributs                       | Équivalent `ssh`              |
|---------------------------|---------------------------------|------------------------------|
| Configuration par défaut  | *(aucun)*                       | `ssh <host>` (fichiers `~/.ssh/`) |
| Utilisateur / mot de passe| `ssh_user`, `ssh_password`      | `ssh user@host`              |
| Clé privée                | `ssh_user`, `ssh_key_file`      | `ssh -i key.pem user@host`   |

### Élévation de privilèges

`apt`, `service` et `sysctl` ont besoin des droits root sur la cible et passent
par `sudo` avec mot de passe (un seul `sudo -S -p '' sh -c '<commande>'` par
action, jamais `sudo -n`/NOPASSWD). Le mot de passe utilisé est celui de
`ssh_password` dans l'inventory — **y compris pour un hôte qui se connecte en
SSH par clé** (`ssh_key_file`). Renseigne donc `ssh_password` dès qu'un de ces
trois modules cible cet hôte, même si `ssh_key_file` est aussi présent. Sans mot
de passe, ces modules lèvent une erreur explicite plutôt que d'échouer
silencieusement.

`copy` et `template` utilisent aussi `sudo` quand `ssh_password` est renseigné :
les fichiers sont déposés dans un dossier temporaire (`mktemp -d`), puis mis en
place par un seul `sudo install -D -m <mode>` (droits du fichier local
conservés). Sans mot de passe, ils écrivent directement avec les droits de
l'utilisateur SSH.

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
python -m pycodestyle mla/ tests/
python -m pytest -q
```

`pyproject.toml` configure `pytest` (`pythonpath = ["."]`) pour que les fichiers
de `tests/` puissent faire `from mla... import ...` quel que soit le dossier
depuis lequel `pytest` est lancé.

Le code doit respecter la PEP8 ; `print` est interdit, tout passe par `logging`.

## Environnement de test local

Deux conteneurs Debian + systemd + sshd pour tester les trois modes d'auth et
l'idempotence, sans machines distantes. Voir [`docker/README.md`](docker/README.md).
C'est un outillage de test local optionnel : `mla` n'en dépend pas.
