# MyLittleAnsible

Un mini-Ansible écrit en Python : `mla` configure des serveurs Linux par SSH
à partir d'un inventaire et d'un playbook YAML déclaratifs.

## Contexte

Projet réalisé en binôme pour le module TIC-NUX4 de l'ETNA. L'objectif était de
reconstruire le cœur d'un outil d'*infrastructure as code* comme Ansible :
décrire l'état voulu des machines (paquets installés, services, fichiers,
paramètres du noyau…) et laisser l'outil faire converger chaque hôte, sans
rien modifier quand l'état est déjà atteint.

Contraintes du projet : Python 3.11, uniquement la bibliothèque standard plus
`paramiko`, `pyyaml`, `jinja2` et `click`, code conforme à la PEP 8, aucun
`print` (toute la sortie passe par `logging`).

## Fonctionnalités

- **6 modules** : `apt`, `copy`, `template`, `service`, `sysctl`, `command`.
- **3 méthodes d'authentification SSH**, au choix pour chaque hôte :
  configuration par défaut (`~/.ssh/`), utilisateur et mot de passe, ou clé
  privée.
- **Idempotence** : chaque module lit d'abord l'état de l'hôte et ne fait rien
  s'il est déjà conforme. Le résultat est `OK` (rien à faire), `CHANGED`
  (modification appliquée) ou `KO` (échec).
- **`--dry-run`** : affiche les commandes qui seraient exécutées sans rien
  modifier. Seules des lectures sont faites sur les hôtes.
- **`--debug`** : affiche les stack traces complètes en cas d'erreur.
- **Élévation de privilèges** par `sudo` avec mot de passe. Le mot de passe est
  masqué dans tous les logs.
- **Bilan par hôte** en fin d'exécution (`ok`, `changed`, `fail`). Le code de
  sortie est non nul dès qu'un hôte a échoué.

## Installation

Prérequis : Python 3.11 ou plus récent et un accès SSH aux hôtes cibles. Les
modules `apt`, `service` et `sysctl` visent des cibles Debian ou Ubuntu avec
systemd.

```sh
git clone https://github.com/Mvth1s/MyLittleAnsible.git
cd MyLittleAnsible
python -m venv .venv
source .venv/bin/activate          # bash / zsh
source .venv/bin/activate.fish     # fish
pip install -r requirements.txt
pip install -e .                   # installe la commande `mla`
```

## Utilisation

```sh
mla -f todos.yml -i inventory.yml
```

| Option      | Rôle                                                                   |
|-------------|-------------------------------------------------------------------------|
| `-f`        | playbook (liste de todos) à exécuter                                    |
| `-i`        | inventaire décrivant les hôtes cibles                                   |
| `--debug`   | affiche les stack traces en cas d'erreur (masquées par défaut)          |
| `--dry-run` | n'applique rien, affiche seulement les commandes qui seraient exécutées |

### Inventaire

```yaml
hosts:
  webserver:
    ssh_address: 192.168.1.22
    ssh_port: 2222
    ssh_user: deploy
    ssh_key_file: ~/.ssh/id_ed25519
    ssh_password: mot-de-passe-sudo   # requis pour apt/service/sysctl
  bastion:
    ssh_address: 192.168.1.24        # config par défaut : comme `ssh 192.168.1.24`
```

`ssh_address` est obligatoire. `ssh_port` est un entier entre 1 et 65535 ; s'il
est absent, le port vient de `~/.ssh/config` (`Port`), sinon c'est `22`.
[`inventory.example.yml`](inventory.example.yml) détaille les trois méthodes
d'authentification :

| Méthode                     | Attributs                  | Équivalent `ssh`                  |
|-----------------------------|----------------------------|-----------------------------------|
| Configuration par défaut    | *(aucun)*                  | `ssh <host>` (fichiers `~/.ssh/`) |
| Utilisateur et mot de passe | `ssh_user`, `ssh_password` | `ssh user@host`                   |
| Clé privée                  | `ssh_user`, `ssh_key_file` | `ssh -i key.pem user@host`        |

Si `ssh_key_file` et `ssh_password` sont tous deux renseignés, la clé est
essayée en premier, puis le mot de passe si la clé est refusée. Sans `ssh_user`
ni `User` dans `~/.ssh/config`, `mla` utilise l'utilisateur courant.

### Playbook (todos)

Un playbook est une liste de todos, exécutées dans l'ordre sur tous les hôtes :

```yaml
- module: apt
  params:
    name: nginx
    state: present

- module: copy
  params:
    src: ./public
    dest: /var/www/public
    backup: true

- module: template
  params:
    src: default.conf.j2
    dest: /etc/nginx/sites-enabled/default
    vars:
      listen_port: 8000
      server_name: "_"

- module: service
  params:
    name: nginx
    state: restarted

- module: sysctl
  params:
    attribute: net.core.somaxconn
    value: 8192
    permanent: true

- module: command
  params:
    command: |
      echo "test" > /tmp/dummy-file
      cat /tmp/dummy-file
```

| Module     | Rôle                                               | Paramètres (défaut)                                                            |
|------------|----------------------------------------------------|--------------------------------------------------------------------------------|
| `apt`      | installe ou désinstalle un paquet APT              | `name`, `state` (`present` / `absent`, défaut `present`)                       |
| `copy`     | copie un fichier ou un dossier local vers la cible | `src`, `dest`, `backup` (défaut `false`)                                       |
| `template` | rend un template Jinja2 sur la cible               | `src`, `dest`, `vars`                                                          |
| `service`  | pilote un service systemd                          | `name`, `state` (`started`, `restarted`, `stopped`, `enabled`, `disabled`)     |
| `sysctl`   | modifie un paramètre du noyau                      | `attribute`, `value`, `permanent` (défaut `false`)                             |
| `command`  | exécute une commande shell                         | `command`, `shell` (défaut `/bin/bash`)                                        |

Le dépôt fournit deux playbooks prêts à l'emploi : [`todos.yml`](todos.yml)
(nginx, copie d'un site, démarrage du service) et
[`todos-full.yml`](todos-full.yml), qui utilise les six modules.

## Exemple de sortie

`todos-full.yml` lancé deux fois sur deux conteneurs neufs. Au premier passage,
tout est à appliquer :

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
2026-10-13 13:26:03,993 - root - INFO - [7] host=172.28.0.11 op=command command=echo "test" > /tmp/dummy-file cat /tmp/dummy-file shell=/bin/bash
2026-10-13 13:26:03,993 - root - INFO - [7] host=172.28.0.12 op=command command=echo "test" > /tmp/dummy-file cat /tmp/dummy-file shell=/bin/bash
2026-10-13 13:26:03,996 - root - INFO - [7] host=172.28.0.11 op=command status=CHANGED
2026-10-13 13:26:04,037 - root - INFO - [7] host=172.28.0.12 op=command status=CHANGED
2026-10-13 13:26:04,037 - root - INFO - done processing tasks for hosts: 172.28.0.11, 172.28.0.12
2026-10-13 13:26:04,037 - root - INFO - host=172.28.0.11 ok=1 changed=6 fail=0
2026-10-13 13:26:04,037 - root - INFO - host=172.28.0.12 ok=1 changed=6 fail=0
```

Au second passage, l'idempotence joue : seuls `service state=restarted` et
`command` restent `CHANGED`, ce qui est voulu (voir
[Limites connues](#limites-connues)). `service state=enabled` est déjà `OK` au
premier passage, car le paquet nginx active lui-même le service à
l'installation.

```
2026-10-13 13:26:04,712 - root - INFO - done processing tasks for hosts: 172.28.0.11, 172.28.0.12
2026-10-13 13:26:04,712 - root - INFO - host=172.28.0.11 ok=5 changed=2 fail=0
2026-10-13 13:26:04,712 - root - INFO - host=172.28.0.12 ok=5 changed=2 fail=0
```

En `--dry-run`, chaque commande qui serait exécutée est loguée sans le mot de
passe ni l'enveloppe `sudo`. Les retours à la ligne y sont écrits `\n` pour que
chaque entrée tienne sur une ligne :

```
host=172.28.0.11 dry run: systemctl restart nginx
host=172.28.0.11 dry run: /bin/bash -c 'echo "test" > /tmp/dummy-file\ncat /tmp/dummy-file'
```

## Architecture

```
mla/
├── cli.py          point d'entrée click (-f, -i, --debug, --dry-run)
├── inventory.py    lecture et validation de l'inventaire -> objets Host
├── todos.py        lecture du playbook et orchestration (run_todos)
├── ssh.py          connexion SSH (3 modes d'auth) et run_remote_cmd
├── logger.py       format des logs, masquage des secrets, troncature
└── modules/
    ├── base.py     BaseModule, ModuleResult, ModuleError, helpers sudo et upload
    ├── apt.py      ├── copy.py     ├── template.py
    └── service.py  ├── sysctl.py   └── command.py
tests/              un fichier de tests par module, fixtures YAML dans fixtures/
docker/             deux hôtes Debian 12 jetables pour les essais
```

Le flux d'une exécution :

1. `cli.py` configure le logging, charge l'inventaire et le playbook.
2. `run_todos` ouvre une connexion SSH par hôte, puis exécute chaque todo sur
   chaque hôte, dans l'ordre du playbook.
3. Pour chaque todo, la classe du module est instanciée avec ses `params`, puis
   sa méthode `process(ssh_client, dry_run, sudo_password)` est appelée.

**`BaseModule`** définit cette interface commune. Chaque module en hérite,
déclare son `name` et ses `DEFAULTS` (valeurs des paramètres optionnels
affichées dans l'en-tête de tâche), et implémente `process`. Celle-ci retourne
un `ModuleResult` (`changed`, commandes du dry-run, avertissements) ou lève
`ModuleError`. Ajouter un module revient donc à écrire une classe et à
l'enregistrer dans `mla/modules/__init__.py`.

**`run_remote_cmd`** (`ssh.py`) est le seul point d'exécution distante. Il
lance une commande sur le client paramiko, écrit éventuellement des données
sur l'entrée standard du canal, puis renvoie un `CmdResult` (`stdout`,
`stderr`, `exit_code`). Au-dessus, `base.py` fournit `run_checked` (lève
`ModuleError` si le code de retour est non nul), `run_sudo` et `upload`
(dépôt de fichiers par SFTP).

## Choix techniques

- **Lecture de `~/.ssh/config`** : comme `ssh <host>`, `mla` applique
  `HostName`, `User`, `Port` et `IdentityFile` quand l'inventaire ne les précise
  pas. L'inventaire reste prioritaire et un fichier absent est ignoré.
  `ssh_address` peut donc être un alias défini dans `~/.ssh/config`.
- **Mot de passe sudo passé par stdin** : `apt`, `service` et `sysctl` passent
  par un unique `sudo -S -p '' sh -c '<commande>'` par action. Le mot de passe
  (celui de `ssh_password`, y compris pour un hôte connecté par clé) est écrit
  sur l'entrée standard du canal SSH, jamais dans la ligne de commande : il
  n'apparaît pas dans `ps` sur la cible. Sans mot de passe, ces modules
  échouent avec une erreur explicite plutôt que de dépendre d'un `NOPASSWD`.
- **Dépôt de fichiers en un seul sudo** : avec un mot de passe, `copy` et
  `template` déposent les fichiers dans un dossier temporaire (`mktemp -d`),
  puis les mettent en place avec un seul `sudo install -D -m <mode>`, en
  conservant les droits du fichier local. Sans mot de passe, ils écrivent
  directement avec les droits de l'utilisateur SSH.
- **Secrets masqués** : la valeur de `ssh_password` est remplacée par
  `********` dans toutes les lignes de log, même avec `--debug`.
- **Variables de template manquantes** : une variable absente de `vars` (et non
  protégée par `| default(...)` ou `is defined`) est rendue vide, et un warning
  `template variable '<nom>' is undefined (rendered empty)` est logué une fois
  par variable et par hôte. Le fichier rendu garde son retour à la ligne final.
- **Libellé IP:port** : chaque ligne liée à un hôte commence par `host=<IP>`.
  Si plusieurs hôtes de l'inventaire partagent la même IP (par exemple
  `127.0.0.1` avec des ports différents), le libellé devient `host=<IP>:<port>`.
- **Timeouts** : la connexion abandonne après 10 s, à chacune des trois étapes
  (TCP, bannière SSH, authentification). L'erreur est loguée une fois, puis
  chaque todo affiche `status=KO` pour cet hôte, sans bloquer les autres.
- **Logs sur une ligne** : les sorties d'erreur multi-lignes (stderr de
  `systemctl`…) sont jointes par ` | ` et tronquées à 200 caractères.
- **`sysctl` idempotent** : les booléens deviennent `1`/`0` et les espaces des
  valeurs multiples sont normalisés (`"32768 60999"` reste `OK` au second
  passage). Avec `permanent: true`, la ligne `attribut = valeur` remplace toute
  ligne existante pour cet attribut dans `/etc/sysctl.d/99-mla.conf`.
- **`copy` vers un dossier** : si `dest` se termine par `/`, le fichier est
  déposé dans ce dossier sous son nom, et le dossier est créé si besoin.

## Environnement de test Docker

Le dossier [`docker/`](docker/README.md) fournit deux hôtes Debian 12 jetables
(`172.28.0.11` et `172.28.0.12`) qui démarrent systemd et sshd, avec un
utilisateur `mla` (mot de passe `mla`) et `sudo` avec mot de passe. Après avoir
généré la clé de test (étape 1 de [`docker/README.md`](docker/README.md)),
depuis la racine du dépôt :

```sh
cp inventory.example.yml inventory.yml
(cd docker && docker compose up -d --build)
mla -f todos-full.yml -i inventory.yml
```

Cet environnement est optionnel : `mla` n'en dépend pas.

## Tests

```sh
pip install -r requirements-dev.txt
python -m pytest -q
python -m pycodestyle mla/ tests/
```

Les tests unitaires (pytest) simulent le client SSH : ils ne demandent ni
réseau ni conteneur. `pyproject.toml` ajoute la racine du dépôt au
`pythonpath`, pour que `from mla... import ...` fonctionne quel que soit le
dossier de lancement. La CI GitHub Actions lance les tests et pycodestyle à
chaque push et pull request.

## Limites connues

- **Exécution séquentielle** : les hôtes sont traités l'un après l'autre, sans
  parallélisme.
- **Pas de timeout sur les commandes** : seule la connexion est bornée à 10 s ;
  une commande distante qui ne se termine jamais bloque l'exécution.
- **Toujours `CHANGED`** : `service` avec `state: restarted` et `command` ne
  peuvent pas savoir si l'état voulu est déjà atteint. Ils s'exécutent et
  renvoient `CHANGED` à chaque passage.
- **Cibles Debian/Ubuntu** : `apt` suppose APT, `service` suppose systemd.
- **Playbook minimal** : pas de variables globales, de conditions, de boucles,
  de handlers ni de rôles.
- **Chemins `src` relatifs** (`copy`, `template`) : ils sont résolus depuis le
  dossier courant au lancement de `mla`, pas depuis l'emplacement du playbook.

## Auteurs

- [Mvth1s](https://github.com/Mvth1s)
- aguado_m

## Licence

Distribué sous licence MIT. Voir [`LICENSE`](LICENSE).
